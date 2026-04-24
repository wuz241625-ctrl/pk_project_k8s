import functools
import re

from marshmallow import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from tornado.web import MissingArgumentError

from application.lakshmi_api.base import ApiError, ApiInfo, BearerTokenError
from application.lakshmi_api.services.error_manager import ErrorManager
from application.lakshmi_api.exceptions.api_error import NewApiError

def handle_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        self = args[0]
        error_manager = ErrorManager()
        try:
            return await func(*args, **kwargs)
        except NewApiError as error:
            # 使用新的错误管理器处理结构化错误
            self.set_status(400 if error.code == 'INVALID_TRANSITION' else 403)
            # ErrorManager.handle_rest_error已经提供了兼容新旧格式的响应
            error_response = error_manager.handle_rest_error(error.code, 'en')
            
            # 如果NewApiError有自定义消息，则追加到默认消息后面
            if error.message:
                original_message = error_response['error']['message']
                error_response['error']['message'] = f"{original_message}: {error.message}"
                       
            self.write(error_response)
        except ApiError as error:
            self.set_status(403)
            self.write({"error": {"message": str(error)}})
        except ApiInfo as error:
            self.set_status(202)
            self.write({"error": {"message": str(error)}})
        except BearerTokenError:
            self.set_status(401)
            self.write({"error": {"message": str('Bearer token error, please sign in')}})
        except MissingArgumentError as error:
            self.set_status(403)
            self.write({"error": {"message": extract_message(error)}})
        except ValidationError as error:
            message = ''
            for field, errors in error.messages.items():
                message += f'{field} {" ".join(errors)}\n'
            self.set_status(403)
            self.write({"error": {"message": str(message)}})
        except SQLAlchemyError as e:
            # log the exception
            self.logger.error(f"SQLAlchemyError. {str(e)}")
            raise ApiError('An error occurred while committing the changes to the database.')
        except Exception as error:
            class_name = self.__class__.__name__
            method_name = func.__name__
            self.logger.exception(f'{class_name}.{method_name}: {error}')
            self.set_status(400)
            self.write({"error": {"message": str(error)}})
    return wrapper

def extract_message(error):
    match = re.search(r'\((.*?)\)', str(error))
    return match.group(1) if match else str(error)
