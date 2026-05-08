"""TransactionLogger — handles transaction and operation logging for EasyPaisa payouts."""
import os
import json
import time
from decimal import Decimal

import pymysql


class TransactionLogger:
    """Records operation logs and complete transaction records to the database."""

    def __init__(self, redis_client, logger, trace_id_filter, conf: dict):
        self.redis = redis_client
        self.logger = logger
        self.trace_id_filter = trace_id_filter
        self.conf = conf
        self.operation_logs_enabled = True
        self._verify_operation_logs_table()

    def _verify_operation_logs_table(self):
        """验证操作日志表是否存在"""
        try:
            connection = pymysql.connect(
                host=self.conf['mysql_host'],
                user=self.conf['mysql_user'],
                password=self.conf['mysql_password'],
                db=self.conf['mysql_database'],
                charset='utf8mb4'
            )

            with connection.cursor() as cur:
                cur.execute("SHOW TABLES LIKE 'easypaisa_operation_logs'")
                result = cur.fetchone()

                if not result:
                    self.logger.warning("⚠️ easypaisa_operation_logs表不存在，操作日志功能将被禁用")
                    self.operation_logs_enabled = False
                else:
                    self.logger.info("✅ easypaisa_operation_logs表验证成功")
                    self.operation_logs_enabled = True

        except Exception as e:
            self.logger.error(f"验证操作日志表失败: {e}")
            self.operation_logs_enabled = False
        finally:
            if 'connection' in locals():
                connection.close()

    def log_operation(self, operation_type: str, **kwargs):
        """记录EasyPaisa操作日志到数据库

        Args:
            operation_type: 操作类型
            **kwargs: 其他参数，包括：
                - order_code: 订单号
                - from_payment_id: 转出方payment_id
                - from_account_number: 转出方EasyPaisa手机号
                - to_account_number: 转入账号
                - to_account_name: 收款人姓名
                - to_bank_code: 银行代码
                - to_bank_name: 银行名称
                - transfer_type: 转账类型
                - amount: 金额
                - transaction_id: 交易ID
                - status: 状态
                - api_request: API请求数据
                - api_response: API响应数据
                - api_endpoint: API端点
                - request_uuid: 请求UUID
                - error_code: 错误代码
                - error_message: 错误信息
                - process_time: 处理耗时
                - trace_id: 链路追踪ID
        """
        if not self.operation_logs_enabled:
            # 表不存在时，只记录到文件日志
            self.logger.debug(f"操作日志(仅文件): {operation_type} - {kwargs.get('order_code', '')} - {kwargs.get('status', '')}")
            return

        try:
            connection = pymysql.connect(
                host=self.conf['mysql_host'],
                user=self.conf['mysql_user'],
                password=self.conf['mysql_password'],
                db=self.conf['mysql_database'],
                charset='utf8mb4',
                autocommit=True  # 日志记录使用自动提交
            )

            with connection.cursor() as cur:
                sql = """
                    INSERT INTO easypaisa_operation_logs (
                        from_payment_id, from_account_number,
                        to_account_number, to_account_name, to_bank_code, to_bank_name,
                        order_code, operation_type, transfer_type, amount, currency,
                        transaction_id, reference_number, status,
                        before_balance, after_balance,
                        api_request, api_response, api_endpoint, request_uuid,
                        error_code, error_message, process_time, retry_count,
                        ip_address, user_agent, server_process_id, trace_id, process_log
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """

                # 从API响应中提取requestId作为transaction_id（安全处理）
                transaction_id = kwargs.get('transaction_id')  # 先取原有的transaction_id

                # 安全地尝试从API响应中提取requestId
                try:
                    api_response = kwargs.get('api_response')
                    if api_response and isinstance(api_response, dict):
                        data = api_response.get('data')
                        if data and isinstance(data, dict):
                            request_id = data.get('requestId')
                            if request_id and isinstance(request_id, str) and request_id.strip():
                                transaction_id = request_id.strip()  # 使用API响应中的requestId
                except Exception as e:
                    # 如果提取requestId出错，继续使用原有的transaction_id，不影响主流程
                    self.logger.debug(f"提取requestId时出错，使用原有transaction_id: {e}")

                # 序列化JSON数据
                api_request_json = None
                api_response_json = None

                if kwargs.get('api_request'):
                    try:
                        api_request_json = json.dumps(kwargs['api_request'], ensure_ascii=False)
                    except Exception:
                        api_request_json = str(kwargs['api_request'])

                if kwargs.get('api_response'):
                    try:
                        api_response_json = json.dumps(kwargs['api_response'], ensure_ascii=False)
                    except Exception:
                        api_response_json = str(kwargs['api_response'])

                # 获取trace_id
                trace_id = kwargs.get('trace_id') or getattr(self.trace_id_filter, 'trace_id', 'default')

                cur.execute(sql, (
                    kwargs.get('from_payment_id'),                      # from_payment_id
                    kwargs.get('from_account_number'),                  # from_account_number
                    kwargs.get('to_account_number'),                    # to_account_number
                    kwargs.get('to_account_name'),                      # to_account_name
                    kwargs.get('to_bank_code'),                         # to_bank_code
                    kwargs.get('to_bank_name'),                         # to_bank_name
                    kwargs.get('order_code'),                           # order_code
                    operation_type,                                      # operation_type
                    kwargs.get('transfer_type'),                        # transfer_type
                    float(kwargs['amount']) if kwargs.get('amount') else None,  # amount
                    kwargs.get('currency', 'PKR'),                      # currency
                    transaction_id,                                     # transaction_id (使用requestId)
                    kwargs.get('reference_number'),                     # reference_number
                    kwargs.get('status', 'pending'),                    # status
                    float(kwargs['before_balance']) if kwargs.get('before_balance') else None,  # before_balance
                    float(kwargs['after_balance']) if kwargs.get('after_balance') else None,    # after_balance
                    api_request_json,                                    # api_request
                    api_response_json,                                   # api_response
                    kwargs.get('api_endpoint'),                         # api_endpoint
                    kwargs.get('request_uuid'),                         # request_uuid
                    kwargs.get('error_code'),                           # error_code
                    kwargs.get('error_message'),                        # error_message
                    int(kwargs['process_time']) if kwargs.get('process_time') else None,  # process_time
                    kwargs.get('retry_count', 0),                       # retry_count
                    kwargs.get('ip_address', '127.0.0.1'),              # ip_address
                    kwargs.get('user_agent'),                           # user_agent
                    os.getpid(),                                         # server_process_id
                    trace_id,                                            # trace_id
                    kwargs.get('process_log')                           # process_log
                ))

                # 记录日志信息
                if transaction_id:
                    self.logger.debug(f"✅ 操作日志已记录: {operation_type} - {kwargs.get('order_code', '')} - {kwargs.get('status', '')} - transaction_id: {transaction_id}")
                else:
                    self.logger.debug(f"✅ 操作日志已记录: {operation_type} - {kwargs.get('order_code', '')} - {kwargs.get('status', '')}")

                return

        except Exception as e:
            # 日志记录失败不应该影响主业务，只记录到文件日志
            self.logger.warning(f"记录操作日志失败: {e}")
            return
        finally:
            if 'connection' in locals():
                connection.close()

    def log_complete_transaction(self, order_data: dict, account_info: dict, api_request: dict,
                               api_response: dict, status: str, error_message: str = None,
                               transaction_id: str = None, start_time: float = None,
                               before_balance: float = None, after_balance: float = None,
                               process_details: dict = None):
        """记录完整的交易记录（一笔交易一条记录）"""
        process_time = int((time.time() - start_time) * 1000) if start_time else None

        # 提取转入方信息
        to_account = order_data.get('payment_account', '')
        to_name = order_data.get('payment_name', '')
        ifsc_code = order_data.get('ifsc', '')

        # 判断转账类型
        is_pakistan_mobile = self._is_pakistan_mobile_number(to_account)
        if is_pakistan_mobile and ifsc_code.lower() == 'easypaisa':
            transfer_type = "EasyPaisa同行转账"
            operation_type = "transfer_same_bank"
            to_bank_code = "EASYPAISA"
            to_bank_name = "EasyPaisa"
        else:
            transfer_type = "跨行转账到银行卡"
            operation_type = "transfer_cross_bank"
            to_bank_code = ifsc_code
            to_bank_name = self._get_bank_name_by_ifsc(ifsc_code) if ifsc_code else None

        # 提取错误代码
        error_code = None
        if api_response and api_response.get('code'):
            error_code = str(api_response.get('code', ''))

        # 构建完整的流程日志
        process_log_json = None
        if process_details:
            try:
                from datetime import datetime

                # 辅助函数：安全转换数值类型为JSON可序列化的格式
                def safe_numeric(value):
                    """安全转换数值类型，处理Decimal等不可JSON序列化的类型"""
                    if value is None:
                        return None
                    if isinstance(value, Decimal):
                        return float(value)
                    if isinstance(value, (int, float)):
                        return value
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return str(value)

                def _calculate_safe_balance_change(after_balance, before_balance):
                    """安全计算余额变化，避免类型错误"""
                    try:
                        if after_balance is None or before_balance is None:
                            return None
                        after_decimal = Decimal(str(after_balance)) if not isinstance(after_balance, Decimal) else after_balance
                        before_decimal = Decimal(str(before_balance)) if not isinstance(before_balance, Decimal) else before_balance
                        balance_change = after_decimal - before_decimal
                        return float(balance_change)
                    except (ValueError, TypeError, Decimal.InvalidOperation) as e:
                        self.logger.warning(f"计算余额变化失败: after_balance={after_balance} ({type(after_balance)}), before_balance={before_balance} ({type(before_balance)}), error={e}")
                        return None

                def safe_dict(data):
                    """递归安全转换字典中的所有Decimal类型"""
                    if data is None:
                        return None
                    if isinstance(data, dict):
                        return {k: safe_dict(v) for k, v in data.items()}
                    elif isinstance(data, (list, tuple)):
                        return [safe_dict(item) for item in data]
                    elif isinstance(data, Decimal):
                        return float(data)
                    else:
                        return data

                self.logger.debug("开始构建process_log...")
                process_log = {
                    'order_code': order_data.get('code'),
                    'process_start': process_details.get('process_start_time', datetime.now().isoformat()),
                    'total_duration_ms': process_details.get('total_duration_ms', 0),
                    'order_received': {
                        'timestamp': process_details.get('order_received_time', datetime.now().isoformat()),
                        'status': 'success',
                        'details': {
                            'order_code': order_data.get('code'),
                            'amount': safe_numeric(order_data.get('amount')),
                            'to_account': order_data.get('payment_account'),
                            'to_name': order_data.get('payment_name'),
                            'to_bankcode': order_data.get('payment_bankcode')
                        }
                    },
                    'risk_check': {
                        'timestamp': process_details.get('risk_check_time', datetime.now().isoformat()),
                        'status': process_details.get('risk_check_status', 'success'),
                        'details': safe_dict(process_details.get('risk_check_details', {}))
                    },
                    'account_selection': {
                        'timestamp': process_details.get('account_selection_time', datetime.now().isoformat()),
                        'status': process_details.get('account_selection_status', 'success'),
                        'details': {
                            'selected_account': account_info.get('phone'),
                            'payment_id': account_info.get('payment_id'),
                            'selection_criteria': process_details.get('account_selection_criteria', 'auto')
                        }
                    },
                    'before_balance_check': {
                        'timestamp': process_details.get('before_balance_time', datetime.now().isoformat()),
                        'status': process_details.get('before_balance_status', 'success'),
                        'details': {
                            'balance': safe_numeric(before_balance),
                            'api_response_time': process_details.get('before_balance_duration', 0)
                        },
                        'error': process_details.get('before_balance_error')
                    },
                    'transfer_api_call': {
                        'timestamp': process_details.get('transfer_api_time', datetime.now().isoformat()),
                        'status': status,
                        'details': {
                            'api_endpoint': api_request.get('action') if api_request else '',
                            'request_uuid': api_request.get('id') if api_request else '',
                            'transfer_type': transfer_type,
                            'api_response_code': api_response.get('code') if api_response else None,
                            'api_duration_ms': process_details.get('api_duration_ms', 0)
                        },
                        'error': error_message if status != 'success' else None
                    },
                    'after_balance_check': {
                        'timestamp': process_details.get('after_balance_time', datetime.now().isoformat()),
                        'status': process_details.get('after_balance_status', 'success'),
                        'details': {
                            'balance': safe_numeric(after_balance),
                            'balance_change': _calculate_safe_balance_change(after_balance, before_balance)
                        },
                        'error': process_details.get('after_balance_error')
                    },
                    'lock_release': {
                        'timestamp': process_details.get('lock_release_time', datetime.now().isoformat()),
                        'status': process_details.get('lock_release_status', 'success'),
                        'details': safe_dict(process_details.get('lock_release_details', {}))
                    },
                    'final_status': {
                        'timestamp': datetime.now().isoformat(),
                        'status': status,
                        'details': {
                            'transaction_id': transaction_id,
                            'final_result': status,
                            'error_message': error_message,
                            'transfer_type': transfer_type,
                            'before_balance': safe_numeric(before_balance),
                            'after_balance': safe_numeric(after_balance)
                        }
                    },
                    'summary': {
                        'total_steps': 8,
                        'success_steps': len([k for k, v in {
                            'order_received': 'success',
                            'risk_check': process_details.get('risk_check_status', 'success'),
                            'account_selection': process_details.get('account_selection_status', 'success'),
                            'before_balance_check': process_details.get('before_balance_status', 'success'),
                            'transfer_api_call': status,
                            'after_balance_check': process_details.get('after_balance_status', 'success'),
                            'lock_release': process_details.get('lock_release_status', 'success'),
                            'final_status': status
                        }.items() if v == 'success']),
                        'final_status': status
                    }
                }

                self.logger.debug("准备序列化process_log...")
                self.logger.debug(f"before_balance类型: {type(before_balance)}, 值: {before_balance}")
                self.logger.debug(f"after_balance类型: {type(after_balance)}, 值: {after_balance}")
                self.logger.debug(f"order_amount类型: {type(order_data.get('amount'))}, 值: {order_data.get('amount')}")

                for section_name, section in process_log.items():
                    if isinstance(section, dict) and 'details' in section:
                        details = section['details']
                        for key, value in details.items():
                            if value is not None and isinstance(value, Decimal):
                                self.logger.warning(f"发现未转换的Decimal类型: {section_name}.details.{key} = {value} (类型: {type(value)})")

                process_log_json = json.dumps(process_log, ensure_ascii=False, separators=(',', ':'))
                self.logger.debug("process_log序列化成功")

            except Exception as e:
                self.logger.error(f"构建流程日志失败: {e}")
                self.logger.error(f"错误类型: {type(e).__name__}")

                problematic_fields = []
                for field_name, field_value in [
                    ('before_balance', before_balance),
                    ('after_balance', after_balance),
                    ('order_amount', order_data.get('amount')),
                    ('total_duration_ms', process_details.get('total_duration_ms') if process_details else None)
                ]:
                    if field_value is not None:
                        field_type = type(field_value).__name__
                        self.logger.error(f"字段检查 - {field_name}: {field_value} (类型: {field_type})")
                        if isinstance(field_value, Decimal):
                            problematic_fields.append(f"{field_name}=Decimal({field_value})")

                if process_details:
                    for key, value in process_details.items():
                        if value is not None and isinstance(value, Decimal):
                            problematic_fields.append(f"process_details.{key}=Decimal({value})")
                            self.logger.error(f"process_details中的Decimal字段: {key} = {value}")

                error_details = f"构建流程日志失败: {str(e)}"
                if problematic_fields:
                    error_details += f" | 可能的问题字段: {', '.join(problematic_fields)}"

                process_log_json = json.dumps({'error': error_details}, ensure_ascii=False)

        # 记录完整的交易信息
        self.log_operation(
            operation_type=operation_type,
            order_code=order_data.get('code'),
            from_payment_id=account_info.get('payment_id'),
            from_account_number=account_info.get('phone'),
            to_account_number=to_account,
            to_account_name=to_name,
            to_bank_code=to_bank_code,
            to_bank_name=to_bank_name,
            transfer_type=transfer_type,
            amount=order_data.get('amount'),
            transaction_id=transaction_id,
            status=status,
            before_balance=before_balance,
            after_balance=after_balance,
            api_request=api_request,
            api_response=api_response,
            api_endpoint=api_request.get('action', '') if api_request else '',
            request_uuid=api_request.get('id', '') if api_request else '',
            error_code=error_code,
            error_message=error_message,
            process_time=process_time,
            retry_count=order_data.get('retry_count', 0),
            process_log=process_log_json
        )

    def _is_pakistan_mobile_number(self, phone_number: str) -> bool:
        """判断是否为巴基斯坦手机号"""
        from jobs.easypaisa.payout.utils import is_pakistan_mobile_number
        return is_pakistan_mobile_number(phone_number)

    def _get_bank_name_by_ifsc(self, ifsc_code: str) -> str:
        """根据IFSC代码获取银行名称"""
        if not ifsc_code:
            return None

        # 简单的银行代码映射，可以根据需要扩展
        bank_mapping = {
            'HBL': 'Habib Bank Limited',
            'NBP': 'National Bank of Pakistan',
            'MCB': 'Muslim Commercial Bank',
            'UBL': 'United Bank Limited',
            'ABL': 'Allied Bank Limited',
            'EASYPAISA': 'EasyPaisa',
            'JAZZCASH': 'JazzCash'
        }

        # 提取前3-4位作为银行代码
        bank_code = ifsc_code[:4].upper()
        for code, name in bank_mapping.items():
            if bank_code.startswith(code):
                return name

        return f'Bank ({ifsc_code})'  # 未知银行，返回代码