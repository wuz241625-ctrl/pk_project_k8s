"""Settlement — financial settlement operations extracted from auto_payout.py."""
import traceback
from decimal import Decimal
from typing import Dict, Any, Optional

import pymysql
import simplejson

from application.balance_idempotency import build_balance_idempotency_key, reserve_balance_idempotency_sync


class Settlement:
    """Handles balance changes, payout success routing, and order refunds."""

    def __init__(self, redis_client, logger, conf: dict):
        self.redis = redis_client
        self.logger = logger
        self.conf = conf
        self.qr_id = None  # Set by caller before handle_payout_success

    def get_cache_result(self, table, keys, condition=None):
        """获取缓存数据（复制自BaseHandler.get_cache_result，同步版本）"""
        try:
            if not condition:
                condition = {'id': 1}

            redis_key = f'cache_info_{table}_{condition["id"]}'
            data_info = self.redis.get(redis_key)

            if data_info:
                # 缓存命中
                data_info = simplejson.loads(data_info, parse_float=Decimal)
                self.logger.info(f"缓存命中: {redis_key}")
            else:
                # 缓存未命中，查询数据库
                data_info = {}
                try:
                    # 创建临时数据库连接
                    connection = pymysql.connect(
                        host=self.conf['mysql_host'],
                        user=self.conf['mysql_user'],
                        password=self.conf['mysql_password'],
                        db=self.conf['mysql_database'],
                        charset='utf8mb4',
                        cursorclass=pymysql.cursors.DictCursor
                    )

                    try:
                        # 构建WHERE条件 (对于sys_info表，默认查询id=1)
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
                                # 存入缓存
                                self.redis.set(redis_key, simplejson.dumps(data_info))
                                self.logger.info(f"缓存数据已更新： {table} {condition}")
                    finally:
                        connection.close()

                except Exception as e:
                    self.logger.error(f"查询缓存数据失败: table={table}, condition={condition}, error={e}")
                    data_info = {}

            # 返回指定字段
            if data_info:
                data_info = data_info if keys == ['*'] else {key: data_info[key] for key in keys if key in data_info}

            return data_info

        except Exception as e:
            self.logger.error(f"获取缓存数据失败: table={table}, keys={keys}, condition={condition}, error={e}")
            return {}

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

    # PLACEHOLDER_CHANGE_BALANCE

    def change_balance(self, conn, cur, table, user_id, amount, code, record_type, remark=None, merchant_code=None):
        """余额变更方法（复制自BaseHandler.change_balance，同步版本）"""
        sql_update = f'update {table} set balance=balance + %s where id = %s'
        sql_select = f"select balance{',vip' if table == 'partner' else ''} from {table} where id = %s"
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        sql_select_vip = "select vip,conditions from vip"
        sql_update_vip = "update partner set vip=%s where id = %s"
        sql_select_orders = f"SELECT merchant_code FROM orders_df WHERE code = '{code}' UNION SELECT merchant_code FROM orders_ds WHERE code = '{code}'"

        try:
            user_type = 0 if table == 'partner' else 1
            idempotency_key = build_balance_idempotency_key(code, user_type, user_id, amount, record_type)
            if idempotency_key and not reserve_balance_idempotency_sync(
                cur, idempotency_key, code, user_type, user_id, amount, record_type, self.logger
            ):
                self.logger.info(
                    f"余额流水幂等命中，跳过重复变更 code={code} user_type={user_type} user_id={user_id} record_type={record_type}"
                )
                return True
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

    # PLACEHOLDER_CHANGE_BALANCE_CONT

            # 步骤5: 确定用户类型
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

            self.logger.info(f"全部步骤完成: 用户{user_id}余额从{balance_before}变更为{balance_after}（变更{amount}）")
            return True

        except Exception as e:
            import traceback as tb
            self.logger.error(f"异常发生: {type(e).__name__}: {e}")
            self.logger.error(f"参数: table={table}, user_id={user_id}, amount={amount}, code={code}, record_type={record_type}, remark={remark}, merchant_code={merchant_code}")
            self.logger.error(f"异常堆栈:\n{tb.format_exc()}")
            try:
                self.logger.error(f"尝试获取最后执行的SQL...")
            except:
                self.logger.error(f"无法获取最后执行的SQL")
            return False

    # PLACEHOLDER_HANDLE_PAYOUT

    def handle_payout_success(self, connection, cur, order_data, result):
        """处理代付成功逻辑（复制success_df的核心功能）"""
        try:
            amount = Decimal(order_data['amount'])
            order_code = order_data['code']

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
            if order_type in [1]:
                if order_data.get('status') in [-1, -2]:
                    self.logger.info(f"[{order_code}] 准备扣除商户 {order_data['merchant_id']} 过期订单金额 {order_data['realpay']}。")
                    if not self.change_balance(connection, cur, 'merchant', order_data['merchant_id'], -order_data['realpay'], order_code, 0):
                        return False

            # 3. 商户代理费用计算（复制success_df逻辑）
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

    # PLACEHOLDER_HANDLE_PAYOUT_CONT

            # 4. 码商余额（复制success_df逻辑）
            if order_type in [1, 3]:
                partner_id = order_data['partner_id']
                self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加代付金额 {amount}。")
                if not self.change_balance(connection, cur, 'partner', partner_id, amount, order_code, 1):
                    return False

            # 5. 码商佣金（复制success_df逻辑）
            if order_type in [1]:
                partner_id = order_data['partner_id']
                earn_partner_self = order_data.get('earn_partner_self', 0)
                if earn_partner_self > 0:
                    self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加佣金 {earn_partner_self}。")
                    if not self.change_balance(connection, cur, 'partner', partner_id, earn_partner_self, order_code, 3):
                        return False

            # 6. 代付优惠计算（复制success_df逻辑）
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

            # 8. 更新订单信息，成功结算必须只从执行中(status=1)推进到待通知(status=3)。
            transaction_id = result.get('transaction_id') or result.get('utr') or ''
            if not transaction_id:
                self.logger.warning(f"订单{order_code}未获取到官方交易号，orders_df.utr字段保持原值")
            else:
                self.logger.info(f"订单{order_code}官方交易号: {transaction_id}")
            sql_update = """
                UPDATE orders_df
                SET earn_merchant=%s,
                    status=3,
                    time_payed=NOW(),
                    time_success=NOW(),
                    utr=CASE
                        WHEN (utr IS NULL OR utr = '') THEN %s
                        ELSE utr
                    END
                WHERE code=%s AND status=1
                LIMIT 1
            """
            cur.execute(sql_update, (earn_merchant, transaction_id, order_code))
            if cur.rowcount == 0:
                self.logger.warning(f'订单{order_code}状态不是1，成功结算更新失败，跳过通知')
                return False
            self.logger.info(f'更新订单成功态{self._format_sql(cur, sql_update, (earn_merchant, transaction_id, order_code))}')

            self.logger.info(f'订单{order_code}代付成功处理完成，等待外层提交后通知')

            # 9. 新增：标记冷却期成功
            self.mark_order_cooldown_success(order_code)

            return True

        except Exception as e:
            self.logger.error(f'订单{order_code}success处理异常: {e}')
            self.logger.error(traceback.format_exc())
            return False

    def mark_order_cooldown_success(self, order_code):
        """标记冷却期成功 — stub, overridden by caller or subclass."""
        pass

    def reject_order_with_refund(self, order_data: Dict, connection, reason: str,
                                 selected_account: Dict) -> Dict:
        """
        驳回订单并退回商户余额

        返回：
        - {'success': False, 'reject': True, 'message': ...} 驳回操作完成（待提交）
        - {'success': False, 'reject': False, 'message': ...} 驳回操作失败
        """
        order_code = order_data['code']
        max_remark_bytes = 64

        reason_bytes = reason.encode('utf-8')
        if len(reason_bytes) > max_remark_bytes:
            sys_remark = reason_bytes[:max_remark_bytes].decode('utf-8', errors='ignore')
            sys_remark = sys_remark.rstrip('(:：')
        else:
            sys_remark = reason

        self.logger.warning(f'开始驳回订单: {order_code}, 原因: {reason}')

        try:
            cur = connection.cursor()

            # 1. 查询流水记录
            sql_select_record = """
                SELECT amount, user_type, user_id
                FROM balance_record
                WHERE code=%s AND user_type=1
            """
            cur.execute(sql_select_record, (order_code,))
            mer_records = cur.fetchall()

            self.logger.info(f'订单{order_code}商户流水记录: {len(mer_records)}条')

            # 2. 退回商户余额
            for record in mer_records:
                if not self.change_balance(
                    connection, cur, 'merchant', record['user_id'],
                    -record['amount'],
                    order_code,
                    record_type=9,
                    remark=sys_remark
                ):
                    self.logger.error(f'订单{order_code}退回商户{record["user_id"]}余额失败')
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
                return {'success': False, 'reject': False, 'message': 'Status update failed'}

            self.logger.info(f'订单{order_code}驳回操作已完成（待提交），status: 1->-2')

            return {
                'success': False,
                'reject': True,
                'message': f'Order rejected: {reason}'
            }

        except Exception as e:
            self.logger.exception(f'驳回订单{order_code}异常: {e}')
            return {'success': False, 'reject': False, 'message': f'Exception: {str(e)}'}
