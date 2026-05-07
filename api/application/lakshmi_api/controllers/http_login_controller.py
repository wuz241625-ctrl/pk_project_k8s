import logging
from application.lakshmi_api.base import BaseHandler, ApiError, BearerTokenError
from application.lakshmi_api.exceptions.api_error import NewApiError
from application.lakshmi_api.error_handler import handle_errors

# 导入所有银行模块
# from application.app.login.banks.jio_bank import JioBank  # 文件不存在，暂时注释
from application.app.login.banks.easypaisa import EasyPaisa
from application.app.login.banks.jazzcash import JazzCash

class HttpLoginController(BaseHandler):
    """HTTP登录控制器基类"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.login_logger = logging.getLogger(self.__class__.__name__)

    async def _get_request_data(self):
        """获取请求数据"""
        client_ip = await self.get_ip()
        self.logger.info(f"请求开始 - URL: {self.request.path}, Method: {self.request.method}, IP: {client_ip}")

        try:
            await self.authenticate_current_user()
            self.logger.info(f"用户认证成功 - User ID: {getattr(self.current_user, 'id', 'Unknown')}")

            # 从请求体获取数据 (使用Tornado标准方式)
            try:
                files = self.request.files.get("files")
                if not files:
                    self.logger.info(f"原始请求体内容: {self.request.body}")

                # 使用Tornado标准方式处理Form数据
                data = {k: self.get_argument(k) for k in self.request.arguments}
                self.logger.info(f"Form数据解析成功 - 参数数量: {len(data)}")
                self.logger.info(f"解析后的数据: {data}")

            except Exception as e:
                self.logger.error(f"请求数据处理异常: {str(e)}")
                data = {}

            # 添加用户信息
            data['user_id'] = self.current_user.id
            return data

        except ApiError as error:
            self.logger.error(f"API错误: {str(error)}")
            raise NewApiError('10211', f'API error: {str(error)}')
        except BearerTokenError:
            self.logger.warning(f"认证失败: Bearer token错误或缺失")
            raise NewApiError('10211', 'Bearer token error, please sign in')
        except Exception as e:
            self.logger.error(f"HttpLoginController异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'System internal error: {str(e)}')


class PreLogin(HttpLoginController):
    """预登录 - POST /api/v1/login/pre_login"""
    funcName = "预登录"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.pre_login_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            elif bankname == 'jazzcash':
                self.logger.info(f"{self.funcName} JazzCash 调用")
                jazzcash = JazzCash(self)
                result = await jazzcash.pre_login_http(data)
                self.logger.info(f"{self.funcName} JazzCash 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Pre-login system error: {str(e)}')


class GetOtp(HttpLoginController):
    """OTP发送 - POST /api/v1/login/get_otp"""
    funcName = "OTP发送"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.send_otp_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            elif bankname == 'jazzcash':
                self.logger.info(f"{self.funcName} JazzCash 调用")
                jazzcash = JazzCash(self)
                result = await jazzcash.send_otp_http(data)
                self.logger.info(f"{self.funcName} JazzCash 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Send OTP system error: {str(e)}')


class VerifyOtp(HttpLoginController):
    """OTP验证 - POST /api/v1/login/verify_otp"""
    funcName = "OTP验证"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.verify_otp_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            elif bankname == 'jazzcash':
                self.logger.info(f"{self.funcName} JazzCash 调用")
                jazzcash = JazzCash(self)
                result = await jazzcash.verify_otp_http(data)
                self.logger.info(f"{self.funcName} JazzCash 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Verify OTP system error: {str(e)}')


class ActiveAccount(HttpLoginController):
    """账号激活 - POST /api/v1/login/active_account"""
    funcName = "账号激活"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.active_account_http(data)
                self.set_status(410)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            elif bankname == 'jazzcash':
                self.logger.info(f"{self.funcName} JazzCash 调用")
                jazzcash = JazzCash(self)
                result = await jazzcash.active_account_http(data)
                self.logger.info(f"{self.funcName} JazzCash 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Account Active system error: {str(e)}')


class ChangePin(HttpLoginController):
    """PIN修改 - POST /api/v1/login/change_pin"""
    funcName = "PIN修改"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.change_pin_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Pin Change system error: {str(e)}')


class UploadFingerPrint(HttpLoginController):
    """指纹上传 - POST /api/v1/login/upload_fingerprint"""
    funcName = "指纹上传"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        files = self.request.files.get("files")
        if not files:
            self.logger.error(f"{self.funcName} 失败: 获取不到文件")
            return

        data['file'] = files[0]

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.upload_fingerprint_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            elif bankname == 'jazzcash':
                self.logger.info(f"{self.funcName} JazzCash 调用")
                jazzcash = JazzCash(self)
                result = await jazzcash.upload_fingerprint_http(data)
                self.logger.info(f"{self.funcName} JazzCash 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')
            self.write(result)
        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Upload FingerPrint system error: {str(e)}')


class VerifyFingerprint(HttpLoginController):
    """指纹验证 - POST /api/v1/login/verify_fingerprint"""
    funcName = "指纹验证"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            if bankname == 'easypaisa':
                easypaisa = EasyPaisa(self)
                result = await easypaisa.verify_fingerprint_http(data)
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa')

            self.write(result)
        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Verify Fingerprint system error: {str(e)}')


class SecondLogin(HttpLoginController):
    """二次登录 - POST /api/v1/login/second_login"""
    funcName = "二次登录"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            if bankname == 'easypaisa':
                easypaisa = EasyPaisa(self)
                result = await easypaisa.second_login_http(data)
            elif bankname == 'jazzcash':
                jazzcash = JazzCash(self)
                result = await jazzcash.second_login_http(data)
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)
        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Second Login system error: {str(e)}')


class QueryAccts(HttpLoginController):
    """账户查询 - POST /api/v1/login/query_accts"""
    funcName = "账户查询"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.query_accts_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Query Accounts system error: {str(e)}')


class SelectAccts(HttpLoginController):
    """账户选择 - POST /api/v1/login/select_accts"""
    funcName = "账户选择"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.select_accts_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')

            self.write(result)

        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Select Accounts system error: {str(e)}')


class PaymentStatus(HttpLoginController):
    """获取payment状态 - POST /api/v1/login/payment_status"""
    funcName = "获取payment状态"
    @handle_errors
    async def post(self):
        self.logger.info(f"{self.funcName} 处理开始")
        data = await self._get_request_data()
        if data is None:
            self.logger.error(f"{self.funcName} 失败: 无法获取请求数据")
            return

        try:
            # 验证银行类型
            bankname = data.get('bankname', '').lower()
            self.logger.info(f"银行类型验证: {bankname}")

            # Switch 逻辑处理不同银行
            if bankname == 'easypaisa':
                self.logger.info(f"{self.funcName} EasyPaisa 调用")
                easypaisa = EasyPaisa(self)
                result = await easypaisa.payment_status_http(data)
                self.logger.info(f"{self.funcName} EasyPaisa 结果: {result.get('status', 'unknown')}")
            elif bankname == 'jazzcash':
                self.logger.info(f"{self.funcName} JazzCash 调用")
                jazzcash = JazzCash(self)
                result = await jazzcash.payment_status_http(data)
                self.logger.info(f"{self.funcName} JazzCash 结果: {result.get('status', 'unknown')}")
            else:
                raise NewApiError('10212', f'Unsupported bank type: {bankname}, supported banks: easypaisa, jazzcash')
            self.write(result)
        except NewApiError:
            raise  # 重新抛出NewApiError，让error_handler.py处理
        except Exception as e:
            self.logger.error(f"{self.funcName} 异常: {str(e)}", exc_info=True)
            raise NewApiError('10901', f'Payment Status system error: {str(e)}')
