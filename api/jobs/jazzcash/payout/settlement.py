"""
JazzCash Settlement — Balance changes, success/reject handling.
Extracted from jazzcash_auto_payout.py Phase 3 refactoring.
"""
import json
import traceback
import pymysql
import aiohttp
import simplejson
from decimal import Decimal
from typing import Dict

from config import get_config
from application.jazzcash_gateway import build_form_body

conf = get_config()


class Settlement:
    """Handles balance changes, payout success, and order rejection with refund."""

    def __init__(self, redis, logger, config):
        self.redis = redis
        self.logger = logger
        self.config = config
        self.api_url = config.get('jazzcash_api_url', 'http://34.150.42.92:84')
        self.user_id = config.get('jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
        self.secret_key = config.get('jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')
        # Needed by handle_payout_success for payment sys_balance update
        self.qr_id = None

    def _format_sql(self, cur, sql, params=None):
        """格式化SQL用于日志显示（兼容PyMySQL版本）"""
        try:
            # PyMySQL 1.4.6+ 使用 mogrify 方法
            if hasattr(cur, 'mogrify') and params is not None:
                return cur.mogrify(sql, params).decode() if isinstance(cur.mogrify(sql, params), bytes) else cur.mogrify(sql, params)
            elif hasattr(cur, '_last_executed') and cur._last_executed:
                # 兼容老版本或aiomysql
                return cur._last_executed
            else:
                # 简单的参数替换（仅用于日志显示）
                if params:
                    formatted_sql = sql
                    for param in params:
                        formatted_sql = formatted_sql.replace('%s', repr(param), 1)
                    return formatted_sql
                return sql
        except Exception as e:
            # 如果格式化失败，返回原始SQL和参数
            return f"{sql} [参数: {params}]"


    def change_balance(self, conn, cur, table, user_id, amount, code, record_type, remark=None, merchant_code=None):
        """余额变更方法（复制自BaseHandler.change_balance，同步版本）"""
        sql_update = f'update {table} set balance=balance + %s where id = %s'
        sql_select = f"select balance{',vip' if table == 'partner' else ''} from {table} where id = %s"
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        sql_select_vip = "select vip,conditions from vip"
        sql_update_vip = "update partner set vip=%s where id = %s"
        sql_select_orders = f"SELECT merchant_code FROM orders_df WHERE code = '{code}' UNION SELECT merchant_code FROM orders_ds WHERE code = '{code}'"

        try:
            # 步骤1: 获取变更前余额
            params_1 = (user_id,)
            self.logger.info(f"步骤1: 准备查询{table}用户{user_id}的变更前余额")
            self.logger.info(f"执行SQL: {sql_select} 参数: {params_1}")
            if not cur.execute(sql_select, params_1):
                self.logger.error(f"步骤1失败: 查询变更前余额执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_select, params_1)}")
                return False

            user_before = (cur.fetchall())[0]
            balance_before = user_before['balance']
            self.logger.info(f"步骤1成功: 变更前余额={balance_before}")

            # 步骤2: 更新余额
            params_2 = (amount, user_id)
            self.logger.info(f"步骤2: 准备更新{table}用户{user_id}余额，变更金额={amount}")
            self.logger.info(f"执行SQL: {sql_update} 参数: {params_2}")
            if not cur.execute(sql_update, params_2):
                self.logger.error(f"步骤2失败: 更新余额执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_update, params_2)}")
                return False

            self.logger.info(f"步骤2成功: 更改金额{self._format_sql(cur, sql_update, params_2)}")

            # 步骤3: 获取变更后余额
            params_3 = (user_id,)
            self.logger.info(f"步骤3: 准备查询{table}用户{user_id}的变更后余额")
            self.logger.info(f"执行SQL: {sql_select} 参数: {params_3}")
            if not cur.execute(sql_select, params_3):
                self.logger.error(f"步骤3失败: 查询变更后余额执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_select, params_3)}")
                return False

            user_after = (cur.fetchall())[0]
            balance_after = user_after['balance']
            self.logger.info(f"步骤3成功: 变更后余额={balance_after}")

            # 步骤4: 检查余额是否足够（码商最低余额为0）
            partner_balance = 0
            if Decimal(balance_after) < partner_balance:
                self.logger.error(f"步骤4失败: 余额不足，user_id={user_id}, balance_after={balance_after}, 最低要求={partner_balance}")
                return False
            self.logger.info(f"步骤4成功: 余额检查通过")

            # 步骤5: 确定用户类型
            user_type = 0 if table == 'partner' else 1
            self.logger.info(f"步骤5: 用户类型确定为 {user_type} ({'码商' if user_type == 0 else '商户'})")

            # 步骤6: 获取商户订单号
            self.logger.info(f"步骤6: 处理商户订单号，当前merchant_code={merchant_code}")
            if merchant_code is None:
                self.logger.info(f"执行SQL: {sql_select_orders}")
                if cur.execute(sql_select_orders):
                    orders_result = (cur.fetchall())[0]
                    merchant_code = orders_result['merchant_code']
                    self.logger.info(f"步骤6成功: 查询商户订单号{self._format_sql(cur, sql_select_orders, None)}")
                    self.logger.info(f"获取到merchant_code={merchant_code}")
                else:
                    self.logger.info(f"步骤6: 未找到merchant_code，保持为None")
            else:
                self.logger.info(f"步骤6: merchant_code已存在，无需查询")

            # 步骤7: 插入流水记录
            params_7 = (code, user_type, user_id, balance_before, amount, balance_after, record_type, remark, merchant_code)
            self.logger.info(f"步骤7: 准备插入流水记录")
            self.logger.info(f"执行SQL: {sql_insert}")
            self.logger.info(f"参数: {params_7}")
            if not cur.execute(sql_insert, params_7):
                self.logger.error(f"步骤7失败: 插入流水记录执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_insert, params_7)}")
                return False

            self.logger.info(f"步骤7成功: 新增流水{self._format_sql(cur, sql_insert, params_7)}")

            # 步骤8: VIP 等级更新（仅对码商且金额为正数）
            if table == 'partner' and amount > Decimal(0):
                self.logger.info(f"步骤8: 开始处理VIP等级更新")
                _vip = 0
                self.logger.info(f"执行SQL: {sql_select_vip}")
                if not cur.execute(sql_select_vip):
                    self.logger.error(f"步骤8失败: 查询VIP等级失败")
                    self.logger.error(f"失败SQL: {self._format_sql(cur, sql_select_vip, None)}")
                    return False
                vips = cur.fetchall()
                self.logger.info(f"查询到{len(vips)}个VIP等级配置")

                for i in vips:
                    if balance_after >= i['conditions']:
                        _vip = i['vip']

                self.logger.info(f"VIP等级计算: 当前余额={balance_after}, 应达到VIP={_vip}, 原VIP={user_before['vip']}")

                if int(_vip) > user_before['vip']:
                    self.logger.info(f"需要升级VIP: {user_before['vip']} -> {_vip}")
                    self.logger.info(f"执行SQL: {sql_update_vip} 参数: ({_vip}, {user_id})")
                    params_vip = (_vip, user_id)
                    if not cur.execute(sql_update_vip, params_vip):
                        self.logger.error(f"步骤8失败: {user_id}改变VIP失败")
                        self.logger.error(f"失败SQL: {self._format_sql(cur, sql_update_vip, params_vip)}")
                        return False
                    self.logger.info(f"步骤8成功: VIP等级已更新为{_vip}")
                else:
                    self.logger.info(f"步骤8: VIP等级无需更新")
            else:
                self.logger.info(f"步骤8: 跳过VIP更新（table={table}, amount={amount}）")

            self.logger.info(f"🎉 全部步骤完成: 用户{user_id}余额从{balance_before}变更为{balance_after}（变更{amount}）")
            return True

        except Exception as e:
            import traceback
            self.logger.error(f"🚨 异常发生: {type(e).__name__}: {e}")
            self.logger.error(f"参数: table={table}, user_id={user_id}, amount={amount}, code={code}, record_type={record_type}, remark={remark}, merchant_code={merchant_code}")
            self.logger.error(f"异常堆栈:\n{traceback.format_exc()}")
            try:
                self.logger.error(f"尝试获取最后执行的SQL...")
            except:
                self.logger.error(f"无法获取最后执行的SQL")
            return False


    def handle_payout_success(self, connection, cur, order_data, result):
        """处理代付成功逻辑（复制success_df的核心功能）"""
        try:
            amount = Decimal(order_data['amount'])
            order_code = order_data['code']

            # 注意：主流程已经获取了订单锁，这里不需要重复获取

            # 1. 订单类型判断（复制success_df逻辑）
            # 1=常规订单，2=拆单主单，3=拆单子单
            order_type = -1
            if not order_data.get('is_split') and not order_data.get('parent_id'):
                order_type = 1  # 常规订单
            if order_data.get('is_split') and not order_data.get('parent_id'):
                order_type = 2  # 拆单主单
            if order_data.get('parent_id'):
                order_type = 3  # 拆单子单

            self.logger.info(f"[{order_code}] 订单类型: {order_type} (1=常规, 2=拆单主单, 3=拆单子单)")

            # 2. 扣商户余额（过期订单，复制success_df逻辑）
            # #328 & 382, 主单不会走这个逻辑，子单不会直接影响商户金额
            if order_type in [1]:
                if order_data.get('status') in [-1, -2]:
                    self.logger.info(f"[{order_code}] 准备扣除商户 {order_data['merchant_id']} 过期订单金额 {order_data['realpay']}。")
                    if not self.change_balance(connection, cur, 'merchant', order_data['merchant_id'], -order_data['realpay'], order_code, 0):
                        return False

            # 3. 商户代理费用计算（复制success_df逻辑）
            # #328 & 382, 主单不会走这个逻辑，子单不会直接影响商户金额
            earn_merchant = Decimal(0)
            if order_type in [1] and order_data.get('earn_merchant', 0) > Decimal(0):
                sql_select_rates = """select id,rate_df from (select @orgId id, (select rate_df from merchant where id=@orgId) rate_df,
                                    (select @orgId:=pid from merchant where id=@orgId) pid from
                                    (select @orgId:=%s) vars,merchant) t where id is not null order by pid desc"""
                if not cur.execute(sql_select_rates, (order_data['merchant_id'],)):
                    self.logger.error(f"未找到商户{order_data['merchant_id']}的代理费率信息")
                    return False
                merchant_prates = cur.fetchall()

                for k, v in enumerate(merchant_prates):
                        if not k == 0 and v['rate_df']:
                            _amount = amount * (merchant_prates[k - 1]['rate_df'] - v['rate_df'])
                            if _amount == 0:
                                self.logger.info(
                                    '代付订单{code}没有代付费用差,上级商户{id}费率{rate_df} ,本级商户{id2}费率{rate_df2}'.format(
                                        code=order_code,
                                        id=merchant_prates[k - 1]['id'],
                                        rate_df=merchant_prates[k - 1]['rate_df'],
                                        id2=v['id'],
                                        rate_df2=v['rate_df']
                                    ))
                                continue
                            if _amount < 0:
                                self.logger.error(f"商户代理费率错误: _amount={_amount}, 上级费率={merchant_prates[k - 1]['rate_df']}, 当前费率={v['rate_df']}")
                                return False
                            self.logger.info(f"[{order_code}] 准备为商户代理 {v['id']} 增加佣金 {_amount}。")
                            if not self.change_balance(connection, cur, 'merchant', v['id'], _amount, order_code, 3):
                                return False
                            earn_merchant += _amount

            # 4. 码商余额（复制success_df逻辑）
            # #328 & 382，主单不会走这个逻辑
            if order_type in [1, 3]:
                partner_id = order_data['partner_id']

                # 码商代付金额
                self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加代付金额 {amount}。")
                if not self.change_balance(connection, cur, 'partner', partner_id, amount, order_code, 1):
                    return False

            # 5. 码商佣金（复制success_df逻辑）
            # #328 & 382, 主单 & 子单 不会走这个逻辑
            if order_type in [1]:
                partner_id = order_data['partner_id']
                earn_partner_self = order_data.get('earn_partner_self', 0)
                if earn_partner_self > 0:
                    self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加佣金 {earn_partner_self}。")
                    if not self.change_balance(connection, cur, 'partner', partner_id, earn_partner_self, order_code, 3):
                        return False

            # 6. 代付优惠计算（复制success_df逻辑）
            # #328 & 382, 主单 & 子单 不会走这个逻辑
            disprice = Decimal(0)
            if order_type in [1]:
                cache_result = self.get_cache_result('sys_info', ['range_df'])
                range_df = cache_result.get('range_df') if cache_result else None

                if range_df:
                    import json
                    range_df = json.loads(range_df)
                    for i in range(1, 7):
                        if range_df.get('isOpen' + str(i)) == 1:
                            rangemin = Decimal(range_df.get('rangemin' + str(i), 0))
                            rangemax = Decimal(range_df.get('rangemax' + str(i), 0))
                            if rangemin <= amount <= rangemax:
                                disprice = Decimal(range_df.get('disprice' + str(i), 0))
                                self.logger.info(f'代付优惠 disprice:{disprice} rangemin:{rangemin} rangemax:{rangemax} amount:{amount} merchant_id:{order_data["merchant_id"]}')
                                break

                # 代付优惠入库
                if disprice > 0:
                    partner_id = order_data['partner_id']
                    self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加代付优惠 {disprice}。")
                    if not self.change_balance(connection, cur, 'partner', partner_id, disprice, order_code, 10):
                        return False

            # 7. 更新系统余额
            sql_update_payment = "UPDATE payment SET sys_balance=sys_balance+%s WHERE id=%s"
            cur.execute(sql_update_payment, (-amount, self.qr_id))
            self.logger.info(f"更新支付账户{self.qr_id}系统余额: {self._format_sql(cur, sql_update_payment, (-amount, self.qr_id))}")

            # 8. 更新订单信息（状态status=3已在转账成功时更新）
            # 获取付款手机号用于更新utr字段（如果之前未更新）
            payer_phone = result.get('payer_phone', '')
            if not payer_phone:
                self.logger.warning(f"订单{order_code}未获取到付款手机号，utr字段保持原值")
            else:
                self.logger.info(f"订单{order_code}付款手机号: {payer_phone}")

            # 🔥 优化：只更新earn_merchant字段，status=3已在转账成功时更新
            sql_update = "UPDATE orders_df SET earn_merchant=%s WHERE code=%s"
            cur.execute(sql_update, (earn_merchant, order_code))
            self.logger.info(f'更新订单商户佣金{self._format_sql(cur, sql_update, (earn_merchant, order_code))}')

            # 9. 代付资格继续由 payment.payout_status 控制，不再回写旧 Redis 活跃队列
            if self.qr_id:
                self.logger.info(f"代付账户{self.qr_id}成功后保持 MySQL payout_status 最终态，不回写旧活跃队列")

            # 10. Redis通知
            self.redis.publish('order_df_notify', order_code)

            self.logger.info(f'订单{order_code}代付成功处理完成')

            # 11.新增：标记冷却期成功
            self.mark_order_cooldown_success(order_code)

            return True

        except Exception as e:
            self.logger.error(f'订单{order_code}success处理异常: {e}')
            self.logger.error(traceback.format_exc())
            return False


    def reject_order_with_refund(self, order_data: Dict, connection, reason: str,
                                 selected_account: Dict) -> Dict:
        """
        驳回订单并退回商户余额

        ⚠️ 重要说明：
        1. 此函数不会提交或回滚事务，由调用方统一管理事务
        2. 此函数不会放回账号到活跃列表，由调用方在commit成功后执行

        前置条件（由调用方保证）：
        - status 一定是 1（刚从0更新为1）
        - order_type 一定是 1（常规订单）
        - selected_account 一定存在
        - 调用方已在同一事务中更新了 payment_id

        返回：
        - {'success': False, 'reject': True, 'message': ...} 驳回操作完成（待提交）
        - {'success': False, 'reject': False, 'message': ...} 驳回操作失败
        """
        order_code = order_data['code']
        # 截断 remark 避免超过数据库字段长度（按字节计算，balance_record.remark 为 varchar(64)）
        # 直接使用 reason（通常是 API 返回的 msg），保留更多有用信息
        max_remark_bytes = 64

        # 按字节截断 reason
        reason_bytes = reason.encode('utf-8')
        if len(reason_bytes) > max_remark_bytes:
            # 截断并确保不会在多字节字符中间切断
            sys_remark = reason_bytes[:max_remark_bytes].decode('utf-8', errors='ignore')
            # 清理末尾不完整的括号或标点
            sys_remark = sys_remark.rstrip('(:：')
        else:
            sys_remark = reason

        self.logger.warning(f'⚠️ 开始驳回订单: {order_code}, 原因: {reason}')

        try:
            cur = connection.cursor()

            # 1. 查询流水记录（只查商户流水，status=1时还没有码商流水）
            sql_select_record = """
                SELECT amount, user_type, user_id
                FROM balance_record
                WHERE code=%s AND user_type=1
            """
            cur.execute(sql_select_record, (order_code,))
            mer_records = cur.fetchall()

            self.logger.info(f'订单{order_code}商户流水记录: {len(mer_records)}条')

            # 2. 退回商户余额（status=1，码商还没实际付款，只退商户）
            for record in mer_records:
                if not self.change_balance(
                    connection, cur, 'merchant', record['user_id'],
                    -record['amount'],  # 反向操作
                    order_code,
                    record_type=9,  # 9=代付驳回
                    remark=sys_remark
                ):
                    self.logger.error(f'订单{order_code}退回商户{record["user_id"]}余额失败')
                    # 不回滚，由调用方决定
                    return {'success': False, 'reject': False, 'message': 'Refund failed'}
                self.logger.info(f'订单{order_code}已退回商户{record["user_id"]}金额: {record["amount"]}')

            # 3. 更新订单状态为-2（驳回）
            sql_update_cancel = """
                UPDATE orders_df
                SET status = -2, sys_remark = %s
                WHERE code = %s AND status = 1
                LIMIT 1
            """
            cur.execute(sql_update_cancel, (sys_remark, order_code))
            affected_rows = cur.rowcount

            if affected_rows == 0:
                self.logger.warning(f'订单{order_code}状态不是1，驳回更新失败')
                # 不回滚，由调用方决定
                return {'success': False, 'reject': False, 'message': 'Status update failed'}

            self.logger.info(f'✅ 订单{order_code}驳回操作已完成（待提交），status: 1→-2')

            return {
                'success': False,
                'reject': True,  # 标记为驳回
                'message': f'Order rejected: {reason}'
            }

        except Exception as e:
            self.logger.exception(f'驳回订单{order_code}异常: {e}')
            # 不回滚，由调用方决定
            return {'success': False, 'reject': False, 'message': f'Exception: {str(e)}'}


    def update_account_balance_after_transfer(self, payment_id: str, transfer_amount: Decimal):
        """
        转账成功后更新Redis中的账号余额（仅扣减金额）

        Args:
            payment_id: 账号ID
            transfer_amount: 转账金额（正数）

        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            # 1. 更新有序集合中的余额（使用 ZINCRBY 原子操作扣减）
            balance_sorted_set = self.REDIS_KEYS['jazzcash_balance_sorted_set']
            new_balance = self.redis.zincrby(balance_sorted_set, -float(transfer_amount), payment_id)

            # 如果余额变为负数，设置为0（但不移除）
            if new_balance is not None and float(new_balance) < 0:
                self.redis.zadd(balance_sorted_set, {payment_id: 0})
                self.logger.info(f"账号{payment_id}余额扣减后为负({new_balance})，已设置为0")
                new_balance = 0

            # 2. 更新普通缓存的余额（不设置过期时间，由monitor负责）
            balance_key = f"{self.REDIS_KEYS['jazzcash_balance_prefix']}{payment_id}"
            cached_balance = self.redis.get(balance_key)

            if cached_balance:
                old_balance = Decimal(cached_balance.decode())
                new_balance_value = old_balance - transfer_amount
                # 如果扣减后为负数，设置为0
                if new_balance_value < 0:
                    new_balance_value = Decimal('0')
                # 直接SET，不设置过期时间
                self.redis.set(balance_key, str(new_balance_value))
                self.logger.info(f"账号{payment_id}余额已扣减: -{transfer_amount}, 新余额: {new_balance_value}")
            else:
                self.logger.info(f"账号{payment_id}普通缓存无余额记录，仅更新有序集合")

            return True

        except Exception as e:
            self.logger.error(f"更新账号{payment_id}余额失败: {e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            return False

    async def fetch_balance_from_api(self, account_info):
        """
        从API重新获取账号余额（参考easypaisa_monitor.py的实现）
        当Redis缓存不存在时调用此方法
        """
        import base64
        import hashlib
        import uuid
        import json
        import time

        try:
            payment_id = account_info['payment_id']
            phone = account_info.get('phone')

            # 检查必要信息
            if not phone:
                return {
                    'success': False,
                    'error': f'账号{payment_id}缺少手机号信息'
                }

            # 🔥 JazzCash 余额查询只需要 account_id（与 EasyPaisa 不同，不需要 account_accno）
            # 构造payload数据
            payload_data = {
                "account_id": phone  # 手机号
            }
            self.logger.info(f"payment_id {payment_id} JazzCash余额查询，account_id={phone}")

            # 构造内层payload（按照JazzCash文档格式）
            inner_payload = {
                "id": str(uuid.uuid4()),  # 生成UUID
                "action": "queryBalance",
                "payload": payload_data
            }

            secret_key = self.secret_key
            user_id = self.user_id
            api_url = self.api_url

            if not all([secret_key, user_id, api_url]):
                return {
                    'success': False,
                    'error': 'JazzCash API配置不完整'
                }

            form_data = build_form_body(
                inner_payload.get('action'),
                inner_payload.get('payload', {}),
                user_id,
                secret_key,
                request_id=inner_payload.get('id'),
            )

            self.logger.info(f"🔄 为账号{payment_id}({phone})重新获取余额")

            # 发起API请求
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            start_time = time.time()

            # 使用aiohttp发起异步请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_time = time.time() - start_time

                    if not 200 <= response.status < 300:
                        return {
                            'success': False,
                            'error': f'HTTP错误: {response.status}',
                            'response_time': response_time
                        }

                    # 解析响应
                    result = await response.json()

                    if result.get('code') == 200:
                        # 🔥 根据JazzCash文档，余额在 data.data.avaliableBalance 字段
                        data = result.get('data', {})
                        inner_data = data.get('data', {}) if isinstance(data, dict) else {}
                        balance = inner_data.get('avaliableBalance', inner_data.get('availableBalance', 0))

                        self.logger.info(f"✅ 账号{payment_id}({phone})余额获取成功: {balance}")

                        return {
                            'success': True,
                            'balance': balance,
                            'response_time': response_time,
                            'data': result
                        }
                    elif result.get('code') == 501:
                        # 501 AccountInvalid - 账号无效
                        error_msg = result.get('msg', result.get('message', '账号无效(501)'))

                        return {
                            'success': False,
                            'error': error_msg,
                            'response_time': response_time,
                            'should_offline': True
                        }
                    else:
                        return {
                            'success': False,
                            'error': result.get('msg', result.get('message', 'API返回错误')),
                            'response_time': response_time
                        }

        except Exception as e:
            self.logger.error(f"重新获取账号{payment_id}余额异常: {e}")

            return {
                'success': False,
                'error': str(e),
                'response_time': 0
            }



    def set_payment_id_failed(self, payment_id, reason="处理失败", order_data=None, status=1):
        """设置payment_id失败状态 - 20分钟冷却期

        Args:
            payment_id: Payment ID
            reason: 失败原因
            order_data: 完整订单数据（可选）
            status: 状态类型 - 1: 真正失败, 2: 按成功处理, 3: 系统异常
        """
        try:
            import time

            # 安全转换数值类型为JSON可序列化格式
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

            failed_key = f'{self.REDIS_KEYS["payment_id_failed_prefix"]}{payment_id}'

            # 构造JSON格式的Value
            failed_info = {
                'payment_id': payment_id,
                'reason': reason,
                'created_time': time.time(),
                'expire_time': time.time() + 1200,  # 20分钟后过期
                'status': status
            }

            # 如果有订单数据，添加到JSON中
            if order_data:
                failed_info.update({
                    'order_code': order_data.get('code'),
                    'amount': safe_numeric(order_data.get('amount')),  # 安全转换金额
                    'payment_account': order_data.get('payment_account'),
                    'name': order_data.get('name'),
                    'bank_code': order_data.get('bank_code'),
                    'time_created': str(order_data.get('time_accept', '')),  # 🔥 使用time_accept而不是time_created
                    'user_id': order_data.get('user_id'),
                    'channel_id': order_data.get('channel_id')
                })

            # 设置20分钟冷却期，Value为JSON格式
            self.redis.setex(failed_key, 1200, json.dumps(failed_info, ensure_ascii=False))  # 1200秒 = 20分钟

            self.logger.info(f"Payment ID {payment_id} 设置失败冷却期20分钟: {reason}")

            # 使用动态冷却期，Value为JSON格式
            #self.redis.setex(failed_key, cooldown_seconds, json.dumps(failed_info, ensure_ascii=False))

            # 日志显示实际冷却时间
            #cooldown_minutes = cooldown_seconds / 60
            #self.logger.info(f"Payment ID {payment_id} 设置失败冷却期{cooldown_minutes:.1f}分钟({cooldown_seconds}秒): {reason}")
            #if order_data:
            #   self.logger.info(f"存储订单信息: {order_data.get('code')} - {order_data.get('amount')}")

            return True
        except Exception as e:
            self.logger.error(f'设置payment_id失败状态失败: {e}')
            return False

    # ========== 失败记录管理（统一Hash存储） ==========



    def get_cache_result(self, table, keys, condition=None):
        """获取缓存数据（复制自BaseHandler.get_cache_result，同步版本）"""
        try:
            if not condition:
                condition = {'id': 1}

            redis_key = f'cache_info_{table}_{condition["id"]}'
            data_info = self.redis.get(redis_key)

            if data_info:
                data_info = simplejson.loads(data_info, parse_float=Decimal)
                self.logger.info(f"缓存命中: {redis_key}")
            else:
                data_info = {}
                try:
                    connection = pymysql.connect(
                        host=conf['mysql_host'],
                        user=conf['mysql_user'],
                        password=conf['mysql_password'],
                        db=conf['mysql_database'],
                        charset='utf8mb4',
                        cursorclass=pymysql.cursors.DictCursor
                    )
                    try:
                        where_conditions = []
                        where_values = []
                        for key, value in condition.items():
                            where_conditions.append(f"{key} = %s")
                            where_values.append(value)
                        where_clause = " AND ".join(where_conditions)
                        sql = f"SELECT * FROM {table} WHERE {where_clause}"
                        with connection.cursor() as cur:
                            cur.execute(sql, where_values)
                            result = cur.fetchone()
                            if result:
                                data_info = result
                                self.redis.set(redis_key, simplejson.dumps(data_info))
                                self.logger.info(f"缓存数据已更新： {table} {condition}")
                    finally:
                        connection.close()
                except Exception as e:
                    self.logger.error(f"查询缓存数据失败: table={table}, condition={condition}, error={e}")
                    data_info = {}

            if data_info:
                data_info = data_info if keys == ['*'] else {key: data_info[key] for key in keys if key in data_info}
            return data_info
        except Exception as e:
            self.logger.error(f"获取缓存数据失败: table={table}, keys={keys}, condition={condition}, error={e}")
            return {}

    def mark_order_cooldown_success(self, order_code: str):
        """Delegate to account_selector if available, otherwise no-op."""
        # This is called from handle_payout_success. The orchestrator wires this up.
        if hasattr(self, 'account_selector') and self.account_selector:
            self.account_selector.mark_order_cooldown_success(order_code)
        else:
            self.logger.debug(f"mark_order_cooldown_success skipped (no account_selector): {order_code}")
