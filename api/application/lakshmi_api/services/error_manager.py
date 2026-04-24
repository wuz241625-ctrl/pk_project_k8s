from typing import Optional
from ..models.error_message import ErrorMessage
from ..models.error_message_db import ErrorMessageDB
import global_resources

class ErrorManager:
    def __init__(self):
        self.db_orm = global_resources.db_orm

    def get_error(self, code: str, lang: str = 'en') -> Optional[ErrorMessage]:
        """从数据库获取错误消息"""
        if not self.db_orm:
            return ErrorMessage(
                code=code,
                module='system',
                severity='error',
                technical_message='Unknown error',
                zh_title='系统错误',
                zh_message='未知错误',
                en_title='System Error',
                en_message='Unknown error'
            )
        with self.db_orm.sessionmaker() as session:
            db_msg = session.query(ErrorMessageDB).filter(ErrorMessageDB.error_code == code).first()
            
            if not db_msg:
                # 如果找不到对应的错误消息，返回一个通用错误
                return ErrorMessage(
                    code=code,
                    module='system',
                    severity='error',
                    technical_message='Unknown error',
                    zh_title='系统错误',
                    zh_message='未知错误',
                    en_title='System Error',
                    en_message='Unknown error'
                )
                
            return ErrorMessage(
                code=db_msg.error_code,
                module=db_msg.module,
                severity=db_msg.severity,
                technical_message=db_msg.technical_message,
                zh_title=db_msg.zh_title,
                zh_message=db_msg.zh_message,
                zh_action=db_msg.zh_action,
                en_title=db_msg.en_title,
                en_message=db_msg.en_message,
                en_action=db_msg.en_action,
                hi_title=db_msg.hi_title,
                hi_message=db_msg.hi_message,
                hi_action=db_msg.hi_action
            )

    def handle_rest_error(self, error_code: str, lang: str = 'en') -> dict:
        """处理REST API错误，兼容新旧格式"""
        error = self.get_error(error_code, lang)
        localized_message = error.get_localized_message(lang)
        
        # 兼容新旧格式的错误响应
        return {
            'error': {
                'code': error.code,
                'severity': error.severity,
                # 旧格式兼容字段，使用本地化的消息
                'message': localized_message.get('message', error.technical_message),
                # 其他新格式字段
                **localized_message
            }
        }

    def handle_websocket_error(self, error_code: str, lang: str = 'en') -> dict:
        """处理WebSocket错误，兼容新旧格式"""
        error = self.get_error(error_code, lang)
        localized_message = error.get_localized_message(lang)
        
        # 兼容新旧格式的WebSocket错误响应
        return {
            # 新格式字段
            'code': error.code,
            'severity': error.severity,
            'data': localized_message,
            # 旧格式兼容字段
            'message': localized_message.get('message', error.technical_message),
            'status': 'error'  # 旧版WebSocket通常使用status字段
        } 
