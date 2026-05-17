import datetime
import random
import time
import redis
import pymysql
import logging
import threading

from config import get_config
from logging.handlers import TimedRotatingFileHandler

LOG_FILE = "order_timeout.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()


class TimeOutGuard:
    """运行态银行回压校验器。"""
    EASYPAISA_INDEX_DISPATCH_DS = "easypaisa_runtime:index:dispatch_ds"
    INDEX_DISPATCH_DS = EASYPAISA_INDEX_DISPATCH_DS
    JAZZCASH_INDEX_DISPATCH_DS = "jazzcash_runtime:index:dispatch_ds"

    def __init__(self, redis_client):
        self.redis = redis_client

    @staticmethod
    def _is_easypaisa(bank_type_id=None, bank_type=None) -> bool:
        return str(bank_type_id or "") == "97" or str(bank_type or "") == "97"

    @staticmethod
    def _is_jazzcash(bank_type_id=None, bank_type=None) -> bool:
        return str(bank_type_id or "") == "98" or str(bank_type or "") == "98"

    def check(self, payment_id, bank_type_id=None, bank_type=None) -> bool:
        if self._is_easypaisa(bank_type_id=bank_type_id, bank_type=bank_type):
            return bool(self.redis.sismember(self.EASYPAISA_INDEX_DISPATCH_DS, str(payment_id)))
        if self._is_jazzcash(bank_type_id=bank_type_id, bank_type=bank_type):
            return bool(self.redis.sismember(self.JAZZCASH_INDEX_DISPATCH_DS, str(payment_id)))
        return True


def main():
    try:
        connection = pymysql.connect(host=conf['mysql_host'],
                                     user=conf['mysql_user'],
                                     password=conf['mysql_password'],
                                     db=conf['mysql_database'],
                                     charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        order_timeout(connection, rds)
        usdt_charge_timeout(connection, rds) # usdt 充值订单过期
    except Exception as e:
        logging.exception('连接redis或数据库错误')
        return


def order_timeout(conn, rds):
    with conn.cursor() as cur:
        try:
            now = datetime.datetime.now()
            hours_24_ago = now - datetime.timedelta(hours=24)  # 只对24小时内订单进行超时
            mins_5_ago = now - datetime.timedelta(minutes=7)  # 5分钟超时
            # 订单
            # orders_select = """select code,channel_code,partner_id,amount,payment_id, original_amount from orders_ds 
            #                     where status in (0,1,2) and time_create between %s and %s and %s > time_create"""
            # if not cur.execute(orders_select, (hours_24_ago, now, mins_5_ago)):
            #     conn.rollback()
            # 通用超时时间（例如 7 分钟，回到原值）
            mins_general_ago = now - datetime.timedelta(minutes=7)
            # 1002/1003 通道专用超时时间（3 分钟）
            mins_special_ago = now - datetime.timedelta(minutes=3)  
            
            # 订单
            orders_select = """
                SELECT o.code, o.channel_code, o.partner_id, o.amount, o.payment_id, o.original_amount
                FROM orders_ds o
                WHERE o.status IN (0, 1, 2)
                AND o.time_create BETWEEN %s AND %s
                AND (
                    -- 1002 和 1003 通道使用 3 分钟超时
                    (o.channel_code IN (1002, 1003) AND o.time_create < %s)
                    OR
                    -- 其他所有通道使用 7 分钟超时
                    (o.channel_code NOT IN (1002, 1003) AND o.time_create < %s)
                )
            """
            # 注意：execute 的参数列表需要增加一个参数，对应 SQL 中的两个 %s
            if not cur.execute(orders_select, (hours_24_ago, now, mins_special_ago, mins_general_ago)):
                conn.rollback()
            orders = cur.fetchall()
            order_cancel = """update orders_ds set status=-1 where code=%s and status in (0,1,2)"""
            # 退回余额
            sql_back_balance = """update partner set balance=balance+%s where id=%s"""
            sql_select_balance = """select balance from partner where id = %s"""
            sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type) value (%s,%s,%s,%s,%s,%s,0)"""
            partner_id_arr = []
            for i in orders:
                code = i['code']
                partner_id = i['partner_id']
                if partner_id not in partner_id_arr:
                    partner_id_arr.append(partner_id)
                amount = i['amount']
                payment_id = i['payment_id']
                original_amount = i['original_amount']
                logging.info("订单超时,code={code},partner_id={partner_id}".format(code=code, partner_id=str(partner_id)))

                # 获取锁，防止取消的同时回调
                # busy_key = 'order_success_busy_{code}'.format(code=code)
                # if not rds.setnx(busy_key, 1):
                #     logging.warning('正在操作此订单{code}，稍后再执行过期'.format(code=code))
                #     continue
                # rds.expire(busy_key, 5)
                busy_key = f'lock_order_{code}'
                if not rds.setnx(busy_key, 1):
                    logging.warning(f'[订单锁] 订单{code}抢锁失败，正在被处理，跳过')
                    continue
                rds.expire(busy_key, 10)
                logging.info(f'[订单锁] 订单{code}抢锁成功，开始处理')

                # 取消订单
                if not cur.execute(order_cancel, code):
                    rds.delete(busy_key)
                    conn.rollback()
                    continue
                
                # 小数点回调清理：如果是小数点金额，需要清理Redis中的记录
                if payment_id and amount and str(amount) != str(int(amount)):  # 判断是否为小数点金额
                    try:
                        amount_key = f'decimal_amount:{amount:.2f}'
                        cleanup_key = f'decimal_cleanup:{amount:.2f}'
                        release_key = f'{payment_id}:{amount:.2f}'
                        
                        # 从 List 中删除超时的 payment_id
                        removed_count = rds.lrem(amount_key, 1, payment_id)
                        if removed_count > 0:
                            logging.info(f'订单超时清理: 从 {amount_key} 中删除 {payment_id}')
                        
                        # 从 Hash 中删除对应记录
                        rds.hdel(cleanup_key, payment_id)
                        rds.hdel('payment_release_time', release_key)
                        
                        logging.info(f'小数点回调超时清理完成: payment_id={payment_id}, amount={amount}')
                        
                    except Exception as cleanup_error:
                        logging.exception(f'小数点回调超时清理失败: {cleanup_error}')
                
                amount = original_amount or amount
                # 打印中文日志
                logging.info(f"code: {code}, 原始充值金额: {original_amount}, 充值金额: {amount}")
                if partner_id:
                    # 退回余额
                    if not cur.execute(sql_select_balance, partner_id):
                        conn.rollback()
                        rds.delete(busy_key)
                        continue
                    _before = (cur.fetchall())[0]['balance']
                    if not cur.execute(sql_back_balance, (amount, partner_id)):
                        conn.rollback()
                        rds.delete(busy_key)
                        continue
                    if not cur.execute(sql_select_balance, partner_id):
                        conn.rollback()
                        rds.delete(busy_key)
                        continue
                    _after = (cur.fetchall())[0]['balance']
                    if not cur.execute(sql_insert, (code, 0, partner_id, _before, amount, _after)):
                        conn.rollback()
                        rds.delete(busy_key)
                        continue
                    logging.info(
                        "订单超时已完成退款，payment_id=%s 不再回推旧代收队列",
                        payment_id,
                    )
                    key = 'msg_timeout_{partner_id}'.format(partner_id=partner_id)
                    rds.set(key, 1, 60)    # 保持60秒
                rds.delete(busy_key)
        except Exception as e:
            logging.exception('取消失败:{e}'.format(e=e))
            conn.rollback()
        else:
            conn.commit()
        # finally:
        #     conn.close()

    try:
        # 查询码商余额
        sql_select_balance = """select balance from partner where id = %s"""
        # 该扣未扣订单
        sql_bank_record_amount_d = """select * from bank_record where payment_id in (select id from payment where partner_id=%s)  and callback=0 and trade_type=1 and invalid=0 and if_ew=0"""
        # 扣除该扣未扣
        sql_back_balance = """update partner set balance=balance-%s where id=%s"""
        # 该扣未扣状态修改
        sql_bank_record = """update bank_record set if_ew= 1,ew_code=%s where id=%s"""
        # 添加余额流水
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark) value (%s,%s,%s,%s,%s,%s,0, '扣除该扣未扣')"""
        for i in partner_id_arr:
            partner_id = i
            if not partner_id:
                logging.info('partner_id获取为空:{partner_id}，跳过'.format(partner_id=str(partner_id)))
                continue
            if str(partner_id) == "64337":
                logging.info('跳过内部码商:{partner_id}，稍后再执行过期'.format(partner_id=partner_id))
                continue
            with conn.cursor() as partner_id_cur:
                # 检查 order 是否正在处理中
                order_processing_key = f'order_processing:{partner_id}'  # 用于标记 order 的处理状态
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
                # 获取当前线程 ID
                thread_id = threading.get_ident()
                if rds.setnx(order_processing_key, 1):
                    # 锁创建成功
                    logging.info(
                        f"[{timestamp}] 锁成功创建，订单 {order_processing_key} 开始处理 | partner_id: {partner_id} | 线程ID: {thread_id}"
                    )
                    rds.expire(order_processing_key, 10)
                    logging.info(
                        f"[{timestamp}] 锁过期时间设置为 10 秒 | 订单 {order_processing_key}"
                    )
                else:
                    logging.warning(f"time_out: order 已在处理中，放弃处理 partner_id: {partner_id}")
                    continue # 如果 order 在处理中,放弃处理
                if not partner_id_cur.execute(sql_bank_record_amount_d, partner_id):
                    logging.info('该扣未扣订单为空partner_id:{partner_id}，稍后再执行过期'.format(partner_id=partner_id))
                    continue
                _bank_record = partner_id_cur.fetchall()
                for b in _bank_record:
                    amount = b['amount']
                    if not partner_id_cur.execute(sql_select_balance, partner_id):
                        logging.warning('查询码商余额失败partner_id:{partner_id}，稍后再执行过期'.format(partner_id=partner_id))
                        conn.rollback()
                        continue
                    _balance = (partner_id_cur.fetchall())[0]['balance']
                    if _balance < amount:
                        logging.info('码商partner_id:{partner_id}余额{_balance}不够该当前扣未扣订单金额{amount}当前扣未扣订单id{id}'.format(partner_id=partner_id,_balance=_balance, amount=amount, id=b['id']))
                        continue
                    if not partner_id_cur.execute(sql_back_balance, (amount, partner_id)):
                        logging.warning('扣除该扣未扣失败partner_id:{partner_id}'.format(partner_id=partner_id))
                        conn.rollback()
                        continue
                    ew_code = 'EW'+''.join(str(datetime.datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))
                    if not partner_id_cur.execute(sql_bank_record, (ew_code, b['id'])):
                        logging.warning('该扣未扣状态修改失败id{id},partner_id:{partner_id}'.format(id=b['id'], partner_id=partner_id))
                        conn.rollback()
                        continue
                    if not partner_id_cur.execute(sql_select_balance, partner_id):
                        logging.warning('该扣未扣状态修改失败id{id},partner_id:{partner_id}'.format(id=b['id'], partner_id=partner_id))
                        conn.rollback()
                        continue
                    _after = (partner_id_cur.fetchall())[0]['balance']
                    if not partner_id_cur.execute(sql_insert, (ew_code, 0, partner_id, _balance, -amount, _after)):
                        logging.warning('添加余额流水失败ew_code{ew_code},partner_id:{partner_id},_balance{_balance},amount{amount},_after{_after}'.format(ew_code=ew_code,partner_id=partner_id,_balance=_balance,amount=amount,_after=_after))
                        conn.rollback()
                        continue
                    time.sleep(2)
                    if not rds.exists(order_processing_key):
                        logging.warning(f"time_out: order2 已在处理中，放弃处理 partner_id: {partner_id}")
                        conn.rollback()
                        continue  # 如果 order 在处理中，放弃处理
            conn.commit()
    except Exception as e:
        logging.exception('扣除该扣未扣失败:{e}'.format(e=e))
        conn.rollback()

    try:
        keyPatterns = ['order_success_busy_*', 'grab_df_*', 'lock_order_*']
        allKeys = []
        for pattern in keyPatterns:
            allKeys += rds.keys(pattern)
        for key in allKeys:
            ttl = rds.ttl(key)
            if ttl > 60 or ttl == -1:
                logging.info('key未过期删除成功:{i}'.format(i=key))
                rds.delete(key)
    except Exception as e:
        logging.exception('key未过期删除失败:{e}'.format(e=e))
    # finally:
    #     conn.close()

def usdt_charge_timeout(conn, rds):
    with conn.cursor() as cur:
        try:
            now = datetime.datetime.now()
            hours_24_ago = now - datetime.timedelta(hours=24)  # 只对24小时内订单进行超时
            mins_30_ago = now - datetime.timedelta(minutes=30)  # 30分钟超时
            # 订单
            orders_select = """select * from usdt_deposit_orders 
                                where status in (0,1) and created_at between %s and %s and %s > created_at"""
            if not cur.execute(orders_select, (hours_24_ago, now, mins_30_ago)):
                conn.rollback()
            orders = cur.fetchall()
            order_cancel = """update usdt_deposit_orders set status=-1,remark='time out' where serial_number=%s and status in (0,1)"""
            for i in orders:
                code = i['serial_number']
                logging.info("usdt充值订单超时,code={code}".format(code=code))

                # 获取锁，防止取消的同时回调
                busy_key = 'grab_usdt_{code}'.format(code=code)
                if not rds.setnx(busy_key, 1):
                    logging.warning('正在操作此usdt充值订单{code}，稍后再执行过期'.format(code=code))
                    continue
                rds.expire(busy_key, 5)

                # 取消订单
                if not cur.execute(order_cancel, code):
                    rds.delete(busy_key)
                    conn.rollback()
                    continue
                logging.info("usdt充值订单超时，成功,code={code}".format(code=code))
                rds.delete(busy_key)
        except Exception as e:
            logging.exception('取消失败:{e}'.format(e=e))
            conn.rollback()
        else:
            conn.commit()
        finally:
            conn.close()

if __name__ == '__main__':
    main()
    while True:
        time.sleep(30)
        main()
