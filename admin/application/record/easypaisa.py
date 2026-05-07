import base64
import hashlib
import json
import uuid
from datetime import datetime, timedelta
import os
import sys
import time

import aiohttp
import tornado
import pytz

from application.base import BaseHandler
from application.message import msg

# 添加配置路径
parent_directory = os.path.dirname(__file__)  # application/record
grandparent_directory = os.path.dirname(parent_directory)  # application
great_grandparent_directory = os.path.dirname(grandparent_directory)  # ospay2_admin
api_directory = os.path.dirname(great_grandparent_directory)  # api
sys.path.append(os.path.join(api_directory, 'ospay2_api'))

from config import get_config

# 获取配置
conf = get_config()

# EasyPaisa API配置参数
EASYPAISA_API_URL = getattr(conf, 'easypaisa_api_url', 'http://34.150.42.92:83')
EASYPAISA_USER_ID = getattr(conf, 'easypaisa_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
EASYPAISA_SECRET_KEY = getattr(conf, 'easypaisa_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')

# 银行名称常量
BANK_NAME_EASYPAISA = 'EASYPAISA'


class getAccountList(BaseHandler):
    """根据手机号查询账户名下账户列表"""
    
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            if await self.is_null(data, ['phone']):
                return await self.json_response(data=msg[10007])
            
            phone = data['phone']
            self.logger.info(f'[EasyPaisa] 查询账户列表，手机号: {phone}')
            
            # 1. 通过 JOIN 查询 payment 和 bank_type 信息
            bank_sql = 'select bank.id,bank.name from bank_type bank \
                            left join payment p on p.bank_type_id = bank.id \
                            where p.phone = %s limit 1'
            bank_type_results = await self.query(bank_sql, phone)
            
            if len(bank_type_results) == 0:
                self.logger.warning(f'[EasyPaisa] 未找到手机号 {phone} 对应的 payment 或 bank_type 记录')
                return await self.json_response(msg[10007])
            
            bank_type = bank_type_results[0]
            bank_type_id = bank_type.get('id')
            bank_name = bank_type.get('name', '').upper()
            
            # 2. 验证是否为 EasyPaisa 银行
            if bank_name != BANK_NAME_EASYPAISA:
                self.logger.error(f'[EasyPaisa] 银行类型不匹配: 期望 {BANK_NAME_EASYPAISA}, 实际 {bank_name}')
                return await self.json_response(msg[10371])
            
            self.logger.info(f'[EasyPaisa] 手机号 {phone} 验证通过，bank_type_id={bank_type_id}')
            
            # 3. 调用EasyPaisa API
            api_result = await self._call_easypaisa_api('queryAccountList', {
                'account_id': phone
            })
            
            if not api_result['success']:
                self.logger.error(f'EasyPaisa API调用失败: {api_result["error"]}')
                return await self.json_response(msg[10007])
            
            easypaisa_response = api_result['data']
            if easypaisa_response['code'] != 200:
                self.logger.error(f'EasyPaisa API错误: {easypaisa_response.get("msg", "未知错误")}')
                return await self.json_response(msg[10007])
            
            # 成功获取账户列表
            account_list = easypaisa_response['data']
            formatted_accounts = []
            
            for account in account_list:
                formatted_account = {
                    'accno': account.get('accno', ''),
                    'accountName': account.get('accountName', ''),
                    'accountNameUr': account.get('accountNameUr', ''),
                    'accountBalance': account.get('accountBalance', '0.00'),
                    'accountStatus': account.get('accountStatus', ''),
                    'IBAN': account.get('IBAN', ''),
                    'accountLevel': account.get('accountLevel', ''),
                    'accountProfile': account.get('accountProfile', '')
                }
                formatted_accounts.append(formatted_account)
            
            result = dict(
                code=20000, 
                data=formatted_accounts, 
                total=len(formatted_accounts),
                msg='获取账户列表成功'
            )
            return await self.json_response(result)
                
        except Exception as e:
            self.logger.error(f'查询EasyPaisa账户列表异常: {str(e)}')
            return await self.json_response(msg[10007])


class downloadBill(BaseHandler):
    """根据手机号和账户号下载明细账单"""
    
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            if await self.is_null(data, ['phone', 'accno']):
                return await self.json_response(data=msg[10007])
            
            phone = data['phone']
            accno = data['accno']
            from_datetime = data.get('fromDateTime', '')
            to_datetime = data.get('toDateTime', '')
            
            self.logger.info(f'[EasyPaisa] 下载明细账单，手机号: {phone}, 账户号: {accno}, 时间范围: {from_datetime} ~ {to_datetime}')
            
            # 1. 通过 JOIN 查询 payment 和 bank_type 信息
            bank_sql = 'select bank.id,bank.name from bank_type bank \
                            left join payment p on p.bank_type_id = bank.id \
                            where p.phone = %s limit 1'
            bank_type_results = await self.query(bank_sql, phone)
            
            if len(bank_type_results) == 0:
                self.logger.warning(f'[EasyPaisa] 未找到手机号 {phone} 对应的 payment 或 bank_type 记录')
                return await self.json_response(msg[10007])
            
            bank_type = bank_type_results[0]
            bank_type_id = bank_type.get('id')
            bank_name = bank_type.get('name', '').upper()
            
            # 2. 验证是否为 EasyPaisa 银行
            if bank_name != BANK_NAME_EASYPAISA:
                self.logger.error(f'[EasyPaisa] 银行类型不匹配: 期望 {BANK_NAME_EASYPAISA}, 实际 {bank_name}')
                return await self.json_response(msg[10371])
            
            self.logger.info(f'[EasyPaisa] 手机号 {phone} 验证通过，bank_type_id={bank_type_id}')
            
            # 3. 构造API payload
            payload = {
                'account_id': phone,
                'accno': accno
            }
            
            # 添加时间范围参数（按照EasyPaisa文档格式，基于巴基斯坦时区 UTC+5）
            if from_datetime:
                payload['fromDateTime'] = from_datetime
            if to_datetime:
                payload['toDateTime'] = to_datetime
            
            # 如果没有提供时间范围，使用默认值（最近30天）
            if not from_datetime or not to_datetime:
                pk_tz = pytz.timezone('Asia/Karachi')
                now_pk = datetime.now(pk_tz)
                
                if not from_datetime:
                    start_time_pk = now_pk - timedelta(days=30)
                    payload['fromDateTime'] = start_time_pk.strftime('%Y-%m-%d 00:00:00')
                    
                if not to_datetime:
                    payload['toDateTime'] = now_pk.strftime('%Y-%m-%d 23:59:59')
                
                self.logger.info(f'使用默认时间范围: {payload.get("fromDateTime")} ~ {payload.get("toDateTime")}')
            
            # 调用EasyPaisa API
            api_result = await self._call_easypaisa_api('downloadBill', payload)
            
            if not api_result['success']:
                self.logger.error(f'EasyPaisa API调用失败: {api_result["error"]}')
                return await self.json_response(msg[10007])
            
            easypaisa_response = api_result['data']
            if easypaisa_response['code'] != 200:
                self.logger.error(f'EasyPaisa API错误: {easypaisa_response.get("msg", "未知错误")}')
                return await self.json_response(msg[10007])
            
            # 成功获取账单数据
            bill_data = easypaisa_response['data']
            
            result_data = {
                'fileName': bill_data['body'].get('fileName', 'e-statement.pdf'),
                'fileData': bill_data['body'].get('data', ''),
                'transactionReference': bill_data['body'].get('transactionReference', ''),
                'downloadTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            result = dict(code=20000, data=result_data, msg='下载账单成功')
            return await self.json_response(result)
                
        except Exception as e:
            self.logger.error(f'下载EasyPaisa账单异常: {str(e)}')
            return await self.json_response(msg[10007])
    
    async def _call_easypaisa_api(self, action, payload):
        """
        调用EasyPaisa API的通用方法 (参考auto_payout.py实现)
        
        Args:
            action: API动作名称  
            payload: API载荷数据
            
        Returns:
            dict: {'success': bool, 'data': dict, 'error': str}
        """
        try:
            request_id = str(uuid.uuid4())
            
            inner_payload = {
                "id": request_id,
                "action": action,
                "payload": payload
            }
            
            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            
            secret_key = EASYPAISA_SECRET_KEY
            user_id = EASYPAISA_USER_ID
            api_url = EASYPAISA_API_URL
            
            if not all([secret_key, user_id, api_url]):
                self.logger.error('EasyPaisa API配置不完整')
                return {'success': False, 'error': 'EasyPaisa API配置不完整'}
            
            sign_string = data_b64 + secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()
            
            form_data = {
                'user_id': user_id,
                'data': data_b64,
                'sign': sign
            }
            
            self.logger.info(f'调用EasyPaisa API: {action}, payload: {payload}')
            
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_time = time.time() - start_time
                    
                    if not 200 <= response.status < 300:
                        error_msg = f'HTTP错误: {response.status}'
                        self.logger.error(f'EasyPaisa API调用失败: {error_msg}')
                        return {'success': False, 'error': error_msg}
                    
                    response_text = await response.text()
                    self.logger.info(f'EasyPaisa API原始响应: {action}, 内容: {response_text}')
                    
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        self.logger.error(f'EasyPaisa API响应解析失败: {e}, 原始内容: {response_text}')
                        return {'success': False, 'error': f'JSON解析失败: {str(e)}'}
                    
                    self.logger.info(f'EasyPaisa API响应: {action}, 耗时: {response_time:.2f}s')
                    
                    return {
                        'success': True,
                        'data': result,
                        'error': None
                    }
                
        except aiohttp.ClientError as e:
            error_msg = f"网络请求异常: {str(e)}"
            self.logger.error(f'EasyPaisa API网络异常: {error_msg}')
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"调用API异常: {str(e)}"
            self.logger.error(f'EasyPaisa API异常: {error_msg}')
            return {'success': False, 'error': error_msg}


# 为getAccountList类也添加_call_easypaisa_api方法
getAccountList._call_easypaisa_api = downloadBill._call_easypaisa_api
