import datetime
import json
import redis
import pymysql
import traceback
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler
from decimal import Decimal
from collections import defaultdict

LOG_FILE = "weight.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()

#   设定新码、不同成功率的码和优先收款码的权重，用以派单使用
def main():
    try:
        connection = pymysql.connect(host=conf['mysql_host'],
                                     user=conf['mysql_user'],
                                     password=conf['mysql_password'],
                                     db=conf['mysql_database'],
                                     charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    except Exception as e:
        logging.exception('连接redis或数据库错误')
        return

    with connection.cursor() as cur:
        try:
            logging.info(datetime.datetime.now())
            now = datetime.datetime.now()
            hours_4_ago = now - datetime.timedelta(hours=4)
            sql = """SELECT
                    p.id,p.time_create,p.priority_collection,
                    # COUNT( o.id ) AS cnt,
                    # SUM(IF( o.amount > 0, o.amount, 0 )) AS amount,
                    # COUNT(IF( o.STATUS > 2, 1, NULL )) AS success_count,
                    # SUM(IF( o.STATUS > 2, o.amount, 0 )) AS success_amount,
                    CAST(COUNT(IF( o.STATUS > 2, 1, NULL )) / IF(COUNT( o.id ) = 0, 1, COUNT( o.id )) * 100 AS DECIMAL ( 14, 0 )) AS rate 
                FROM
                    payment AS p
                    LEFT JOIN orders_ds AS o ON p.id = o.payment_id AND o.time_create BETWEEN %s AND %s
                GROUP BY
                    p.id
                ORDER BY
                    rate desc;"""
            cur.execute(sql, (hours_4_ago, now))
            payment_infos = cur.fetchall()
            connection.commit()
            logging.info(datetime.datetime.now())

            # 获取所有的在线接单的码
            list_name = 'payment_active_*'
            tmp_keys = rds.keys(pattern=list_name)
            payment_id_online_list = []
            for k in tmp_keys:
                _payment_id_online_list = (rds.lrange(k, 0, -1))
                payment_id_online_list = payment_id_online_list + _payment_id_online_list

            # 写入 payment_weight 表，记录不同成功率下的码数量和id
            days_3_ago = now - datetime.timedelta(days=3)
            payment_weight = [{} for i in range(22)] # 权重 百分比0-19 新码20 优先收款21
            for i in payment_infos:
                if str(i['id']).encode('utf-8') not in payment_id_online_list:
                    # 在线的才写入
                    continue

                # 优先收款
                if i['priority_collection'] == 1:
                    # 超过2小时的失效
                    if not rds.get('priority_collection_{id}'.format(id=str(i['id']))):
                        sql = "update payment set priority_collection=0 where id=%s"
                        if not cur.execute(sql, i['id']):
                            logging.error('设置priority_collection=1异常' + json.dumps(i))
                        continue
                    if payment_weight[21]:
                        payment_weight[21]['payment_ids'] = payment_weight[21]['payment_ids'] + ',' + str(i['id'])
                        payment_weight[21]['payment_numbers'] = payment_weight[21]['payment_numbers'] + 1
                        # payment_weight[20]['weight'] = 100  # 优先收款固定为100
                    else:
                        payment_weight[21]['payment_ids'] = str(i['id'])
                        payment_weight[21]['payment_numbers'] = 1
                        # payment_weight[21]['weight'] = 100  # 优先收款固定为100
                        payment_weight[21]['type'] = 2
                    continue
                # 新码
                if i['time_create'] > days_3_ago:
                    if payment_weight[20]:
                        payment_weight[20]['payment_ids'] = payment_weight[20]['payment_ids'] + ',' + str(i['id'])
                        payment_weight[20]['payment_numbers'] = payment_weight[20]['payment_numbers'] + 1
                        # payment_weight[20]['weight'] = 100  # 新码固定为100
                    else:
                        payment_weight[20]['payment_ids'] = str(i['id'])
                        payment_weight[20]['payment_numbers'] = 1
                        # payment_weight[20]['weight'] = 100  # 新码固定为100
                        payment_weight[20]['type'] = 1
                    continue
                # 按成功率
                step = int(i['rate'] // 5) #按5%为1个阶梯
                if step == 20:
                    step = 19 #成功率100的置为19
                if payment_weight[step]:
                    payment_weight[step]['payment_ids'] = payment_weight[step]['payment_ids'] + ',' + str(i['id'])
                    payment_weight[step]['payment_numbers'] = payment_weight[step]['payment_numbers'] + 1
                    # payment_weight[step]['weight'] = step * 5
                else:
                    payment_weight[step]['payment_ids'] = str(i['id'])
                    payment_weight[step]['payment_numbers'] = 1
                    # payment_weight[step]['weight'] = step * 5
                    payment_weight[step]['type'] = 0
            # 将各类权重写入表
            for index, i in enumerate(payment_weight):
                if i:
                    sql = "update payment_weight set payment_ids=%s,payment_numbers=%s,type=%s, time_updated=NOW() where id=%s"
                    if not cur.execute(sql, (i['payment_ids'], i['payment_numbers'], i['type'], index+1)):
                        logging.error('写入payment_weight记录异常' + json.dumps(i))
                else:
                    # payment_weight里无值的归0
                    sql = "update payment_weight set payment_ids=null,payment_numbers=0,time_updated=NOW() where id=%s"
                    if not cur.execute(sql, index + 1):
                        logging.error('写入payment_weight记录异常2' + json.dumps(i))

            # 批量写入每个码不同的权重值
            sql = "select * from payment_weight"
            cur.execute(sql)
            payment_weight_infos = cur.fetchall()
            connection.commit()
            for i in payment_weight_infos:
                if i['payment_numbers'] and i['payment_numbers'] > 0:
                    payment_ids = [a for a in i['payment_ids'].split(',') if a != '']
                    batch_size = 1000 #批量最多1000个更新
                    for b in range(0, len(payment_ids), batch_size):
                        batch_ids = payment_ids[b:b + batch_size]
                        sql = "update payment set weight=%s where id in ({ids})".format(ids=','.join(str(d) for d in batch_ids))
                        cur.execute(sql, i['weight'])
                        connection.commit()
            logging.info(datetime.datetime.now())
        except Exception:
            logging.exception('记录异常')
            connection.rollback()
        finally:
            connection.close()

# 尽量剔除成功率为0的码
# 1、暂定印度时间07:00到目前为止每个码订单数未到10单，则派单到10单；如果到10单，则计算这时间段前10单订单的成功率，如果低于某个值，则到明天07:00之前，不让接单；
# 2、由前天07:00到目前为止，如果等于20单且20单都是取消，则人工锁定；
# 3、派单有时间间隔，暂定1分钟内每个码派一单；
# 4、内部账户需要从以上机制里剔除！
def get_continuous_failures(orders):
    """
    处理订单数据，找出连续失败的订单，并返回满足条件的订单列表
    :param orders: 所有订单数据（按 payment_id 和 time_create 排序）
    :return: 满足条件的订单列表
    """
    # 过滤时间范围内的订单
    # filtered_orders = [order for order in orders if time_start <= order['time_create'] <= time_end]
    
    # 存储每个 payment_id 的连续失败订单
    payment_failures = defaultdict(list)
    
    # 记录每个 payment_id 连续失败的最大数量
    current_payment_id = None
    consecutive_failures = 0
    max_consecutive_failures = 0  # 用于记录最大连续失败数量
    current_failures = []  # 用于记录连续失败的订单
    failure_dates = set()  # 用于记录失败订单的日期

    for order in orders:
        payment_id = order['payment_id']
        status = order['status']
        order_date = order['time_create'].date()  # 获取订单的日期部分
        
        if payment_id != current_payment_id:
            # 如果 payment_id 发生变化，重新初始化
            if current_payment_id is not None and consecutive_failures >= 10:
                payment_failures[current_payment_id] = {
                    'failures': current_failures,
                    'fail_count': len(current_failures),
                    'max_consecutive_failures': max_consecutive_failures,
                    'failure_dates': failure_dates
                }
            
            current_payment_id = payment_id
            consecutive_failures = 0  # 重新开始计数
            max_consecutive_failures = 0  # 重置最大连续失败计数
            current_failures = []  # 清空当前失败记录
            failure_dates = set()  # 清空失败日期记录

        # 如果订单失败，增加连续失败的计数
        if status == -1:
            consecutive_failures += 1
            max_consecutive_failures = max(max_consecutive_failures, consecutive_failures)
            current_failures.append(order)  # 记录当前失败订单
            failure_dates.add(order_date)  # 记录失败的日期
        else:
            consecutive_failures = 0  # 失败的连续计数归零
            current_failures = []  # 失败订单记录清空

    # 最后处理剩余的 payment_id
    if consecutive_failures >= 10:
        payment_failures[current_payment_id] = {
            'failures': current_failures,
            'fail_count': len(current_failures),
            'max_consecutive_failures': max_consecutive_failures,
            'failure_dates': failure_dates
        }

    # 筛选出满足条件的 payment_id（连续失败订单 >= 10）
    result = {}
    for payment_id, failure_info in payment_failures.items():
        failures = failure_info['failures']
        fail_count = failure_info['fail_count']
        max_consecutive_failures = failure_info['max_consecutive_failures']
        failure_dates = failure_info['failure_dates']

        # 判断是 "临时码" 还是 "死码"
        failure_type = ''
        if fail_count >= 10:
            # 判断是否是连续10单失败（临时码）或连续2天失败（死码）
            if max_consecutive_failures >= 10:
                failure_type = '临时码'  # 连续10单失败
            if len(failure_dates) >= 10:
                failure_type = '死码'  # 连续10天失败

            result[payment_id] = {
                'failures': failures,
                'fail_count': fail_count,
                'max_consecutive_failures': max_consecutive_failures,
                'failure_type': failure_type  # 新增的返回字段，表示解封类型
            }

    return result

def main2():
    try:
        connection = pymysql.connect(host=conf['mysql_host'],
                                     user=conf['mysql_user'],
                                     password=conf['mysql_password'],
                                     db=conf['mysql_database'],
                                     charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    except Exception as e:
        logging.exception('连接redis或数据库错误')
        return

    with connection.cursor() as cur:
        try:
            logging.info(datetime.datetime.now())
            # redis key 前多少单计算成功率
            send_orders_count = rds.get('send_orders_count')
            send_orders_count = int(send_orders_count.decode('utf-8')) if send_orders_count else 10
            logger.info(f"send_orders_count: {send_orders_count}")
            # redis key 前多少单计算成功率的比较值，低于则暂定接单
            success_orders_rate = rds.get('success_orders_rate')
            success_orders_rate = Decimal(success_orders_rate.decode('utf-8')) if success_orders_rate else 10
            logger.info(f"success_orders_rate: {success_orders_rate}")
            # redis key 成功率归0的时间点，即计算时间范围的起始点
            point_in_time = rds.get('point_in_time')
            point_in_time = int(point_in_time.decode('utf-8')) if point_in_time else 7
            logger.info(f"point_in_time: {point_in_time}")
            now = datetime.datetime.now()
            logger.info(f"当前时间: {now}")
            # 创建一个新的datetime对象，该对象代表当天的07:00
            time_target = now.replace(hour=point_in_time, minute=0, second=0, microsecond=0)
            logger.info(f"目标时间点 (time_target): {time_target}")
            # 如果当前时间小于07:00，则time_target减1天
            if now < time_target:
                interval = int((time_target - now).total_seconds())
                time_target -= datetime.timedelta(days=1)
                logger.info(f"当前时间小于目标时间，调整后的 time_target: {time_target}")
            else:
                interval = 24*60*60 - int((now - time_target).total_seconds())
                logger.info(f"当前时间大于或等于目标时间，time_target 不变: {time_target}")

            logger.info(f"当前时间到目标时间的时间间隔: {interval} 秒")
            logger.info("开始执行 SQL 查询，获取内部支付 ID...")
            #获取内部码商的payment_id
            sql = 'select pay.id from payment pay left join  partner p on pay.partner_id = p.id where p.type = 0'
            cur.execute(sql)
            payment_inside = cur.fetchall()
            connection.commit()
            logger.info(f"内部支付 ID 列表: {payment_inside}")
            # print(1111, payment_inside)

            # 执行计算成功率的 SQL 查询
            logger.info("执行计算成功率的 SQL 查询...")
            #对 orders_ds 表进行了一次子查询，并且在子查询中使用了两个变量 @num 和 @group，用来记录每个 payment_id 的订单数量。@num 变量用于跟踪当前 payment_id 的订单数量，@group 变量用于存储上一个处理的 payment_id，要按payment_id和time_create先排序好。然后在 WHERE 子句中过滤出每个 payment_id 的前10个订单， <<用子查询再inner join比直接的left join要快>>
            sql = """
                SELECT
                    p.id,
                    COUNT( o.id ) AS cnt,
                   # SUM(IF( o.amount > 0, o.amount, 0 )) AS amount,
                   # COUNT(IF( o.STATUS > 2, 1, NULL )) AS success_count,
                   # SUM(IF( o.STATUS > 2, o.amount, 0 )) AS success_amount,
                    CAST(COUNT(IF( o.status > 2, 1, NULL )) / IF(COUNT( o.id ) = 0, 1, COUNT( o.id )) * 100 AS DECIMAL ( 14, 0 )) AS rate 
                FROM
                    payment AS p
                    INNER JOIN (
                        SELECT o.id,o.status,o.payment_id, o.time_create,
                            @num := IF(@group = o.payment_id, @num + 1, 1) as row_number,
                            @group := o.payment_id as dummy
                        FROM orders_ds o, (SELECT @num := 0, @group := NULL) as vars
                        WHERE o.time_create BETWEEN %s AND %s
                        ORDER BY o.payment_id, o.time_create DESC
                    ) AS o 
                    ON p.id = o.payment_id
                WHERE o.row_number <= %s
                GROUP BY p.id
                having  cnt =%s"""
            
            logger.info(f"执行的 SQL 查询: {sql}")
            logger.info(f"参数: time_target = {time_target}, now = {now}, send_orders_count = {send_orders_count}")

            cur.execute(sql, (time_target, now, send_orders_count, send_orders_count))
            payment_infos = cur.fetchall()
            connection.commit()
            logger.info(f"查询结果 payment_infos: {payment_infos}")
            logging.info(datetime.datetime.now())
            # print(2222, payment_infos, interval, now , time_target)
            lock_payments = []
            for i in payment_infos:
                logger.info(f"正在处理支付信息: {i}")
                # 内部码商的不在此限制 和 取消限制的不用限制
                # if i['id'] in payment_inside or rds.get('cancel_send_orders_limit_{id}'.format(id=i['id'])):
                #     continue
                
                # 判断是否为内部码商或取消限制
                logging.info(f"开始检查码商 ID: {i['id']} 的限制条件...")

                if i['id'] in payment_inside:
                    logging.info(
                        f"ID: {i['id']} 属于内部码商 (payment_inside)，不受限制，直接跳过处理。\n"
                        f"内部码商列表: {payment_inside}"
                    )
                    continue
                redis_key = f'cancel_send_orders_limit_{i["id"]}'
                redis_status = rds.get(redis_key)
                if redis_status:
                    logging.info(
                        f"ID: {i['id']} 被标记为取消限制状态。\n"
                        f"Redis Key: {redis_key}, Redis Value: {redis_status}"
                    )
                    continue

                logging.info(f"码商 ID: {i['id']} 不属于内部码商，且未取消限制，继续执行后续逻辑处理。")
                
                # 成功率低于 success_orders_rate ， 在point_in_time之前不能接单
                if Decimal(i['rate'])*100 < success_orders_rate:
                    logging.info('{id},前{send_orders_count} 单，成功率{rate}低于{success_orders_rate}，在{point_in_time}之前不能接单，锁定{interval}小时：'.format(id=i['id'], send_orders_count=send_orders_count, rate=i['rate'], success_orders_rate=success_orders_rate, point_in_time=point_in_time, interval=interval/3600))
                    send_orders_ds_limit = "send_orders_ds_limit_{payment_id}".format(payment_id=i['id'])
                    rds.set(send_orders_ds_limit,1, interval)
                    lock_payments.append(i)
                    
            if lock_payments:
                # 发送消息
                grouped_payments = defaultdict(list)
                for i in lock_payments:
                    grouped_payments[i['partner_id']].append(i['id'])

                # 创建消息
                messages = []
                for partner_id, payment_ids in grouped_payments.items():
                    payment_ids_str = ','.join(map(str, payment_ids))
                    content = f"UPI:{payment_ids_str} success rate is too low! Freeze for {round(interval/3600)} hours!"
                    messages.append({'to_id': partner_id, 'content': content})
                create_message(rds, connection, cur, messages)
                
            # 由前天07:00到目前为止，如果等于20单且20单都是取消，则人工锁定 delete 20250208 begin
            # time_target = now.replace(hour=point_in_time, minute=0, second=0, microsecond=0)
            # if now < time_target:
            #     time_target -= datetime.timedelta(days=2)
            # else:
            #     time_target -= datetime.timedelta(days=1)
            # sql = """SELECT
            #                        p.id,
            #                        COUNT( o.id ) AS cnt,
            #                        # SUM(IF( o.amount > 0, o.amount, 0 )) AS amount,
            #                        # COUNT(IF( o.STATUS > 2, 1, NULL )) AS success_count,
            #                        # SUM(IF( o.STATUS > 2, o.amount, 0 )) AS success_amount,
            #                        # CAST(COUNT(IF( o.STATUS > 2, 1, NULL )) / IF(COUNT( o.id ) = 0, 1, COUNT( o.id )) * 100 AS DECIMAL ( 14, 0 )) AS rate, 
            #                        COUNT(IF( o.STATUS = -1, 1, NULL )) AS fail_count
            #                    FROM
            #                        payment AS p
            #                        INNER JOIN (
            #                             SELECT o.id,o.status,o.payment_id, o.time_create,
            #                                 @num := IF(@group = o.payment_id, @num + 1, 1) as row_number,
            #                                 @group := o.payment_id as dummy
            #                             FROM orders_ds o, (SELECT @num := 0, @group := NULL) as vars
            #                             WHERE o.time_create BETWEEN %s AND %s
            #                             ORDER BY o.payment_id, o.time_create DESC
            #                        ) AS o 
            #                        ON p.id = o.payment_id
            #                    GROUP BY
            #                        p.id
            #                    having  cnt = fail_count and cnt >= %s;"""
            # cur.execute(sql, (time_target, now, send_orders_count*2))
            # payment_infos = cur.fetchall()
            # connection.commit()
            # logging.info(datetime.datetime.now())
            # # print(3333, payment_infos)
            # fail_ids = []
            # for i in payment_infos:
            #     # 内部码商的不在此限制 和 取消限制的不用限制
            #     if i['id'] not in fail_ids and i['id'] not in payment_inside and not rds.get('cancel_send_orders_limit_{id}'.format(id=i['id'])):
            #         fail_ids.append(i['id'])

            # # 批量人工锁定
            # batch_size = 1000  # 批量最多1000个更新
            # for b in range(0, len(fail_ids), batch_size):
            #     batch_ids = fail_ids[b:b + batch_size]
            #     str_batch_ids = [str(i) for i in batch_ids]
            #     logging.info('人工锁定：' + ','.join(str_batch_ids))
            #     sql = "update payment set manual_status=1 where id in ({ids})".format(ids=','.join(str(d) for d in batch_ids))
            #     cur.execute(sql)
            #     connection.commit()
            # logging.info(datetime.datetime.now())
            #  delete 20250208 end
            # 计算失败率，连续10单失败的支付码
            # 记录当前时间
            logger.info(f"当前时间: {now}")

            # 计算当天的目标时间
            time_target = now.replace(hour=point_in_time, minute=0, second=0, microsecond=0)
            logger.info(f"计算出的当天目标时间: {time_target}")
            # 统一回溯 10 天
            time_target -= datetime.timedelta(days=10)
            # 最终确定的目标时间
            logger.info(f"最终确定的 time_target: {time_target}")
            
            sql = """
                SELECT p.id AS payment_id, p.partner_id, o.id AS order_id, o.status, o.time_create, p.manual_status
                FROM payment p
                INNER JOIN orders_ds o ON p.id = o.payment_id
                WHERE o.time_create BETWEEN %s AND %s AND p.manual_status=0
                ORDER BY o.payment_id, o.time_create DESC;
            """
            cur.execute(sql, (time_target, now))
            payment_infos = cur.fetchall()
            connection.commit()

            # 调用函数获取连续失败的订单
            result = get_continuous_failures(payment_infos)
            # 获取所有被标记为临时码的 payment_id
            logger.info("初始化变量：pattern = 'send_orders_ds_limit_*', payment_id_list = []")
            pattern = "send_orders_ds_limit_*"
            temp_code_ids = []

            try:
                # 使用 KEYS 获取所有匹配的键
                logger.info("使用 KEYS 命令获取所有匹配的键。")
                keys = rds.keys(pattern)  # 使用 KEYS 命令获取匹配的所有键
                logger.info(f"获取到的键列表: {keys}")

                # 遍历获取的键列表，提取 payment_id
                for key in keys:
                    logger.info(f"处理键：{key}")

                    # 如果键是字节类型，解码为字符串
                    if isinstance(key, bytes):
                        key_str = key.decode('utf-8')
                        logger.info(f"键为字节类型，已解码为字符串：{key_str}")
                    else:
                        key_str = key  # 如果键已经是字符串，直接使用

                    # 判断键是否符合预期模式
                    if key_str.startswith("send_orders_ds_limit_"):
                        logger.info(f"键匹配模式，提取 payment_id。")
                        payment_id = key_str.split('_')[-1]  # 从键中提取 payment_id
                        temp_code_ids.append(payment_id)
                        logger.info(f"提取到的 payment_id: {payment_id}, 已添加到列表。")

                # 输出最终的 payment_id 列表
                logger.info(f"最终的 temp_code_ids: {temp_code_ids}")

            except Exception as e:
                # 捕获整个方法的错误并打印详细信息
                error_details = traceback.format_exc()
                logger.error(f"获取 payment_id 过程中发生错误: {e}\n错误详情:\n{error_details}")
                raise  # 根据需要决定是否重新抛出异常

            # 打印结果
            fail_ids = []
            fail_payments = []
            for payment_id, entry in result.items():
                logger.info(f"Payment ID: {payment_id}, Fail Count: {entry['fail_count']}, Max Consecutive Failures: {entry['max_consecutive_failures']}, Failure Type: {entry['failure_type']}")

                if payment_id in payment_inside:
                    logging.info(
                        f"ID: {payment_id} 属于内部码商 (payment_inside)，不受限制，直接跳过处理。\n"
                        f"内部码商列表: {payment_inside}"
                    )
                    continue

                # 根据 failure_type 输出对应的值
                if entry['failure_type'] == '死码':
                    fail_ids.append(payment_id)
                    fail_payments.append(entry)
                    logger.info(f"发现死码：已加入 fail_ids 和 fail_payments，ID: {payment_id}, 内容: {entry}")

                elif entry['failure_type'] == '临时码' and str(payment_id) not in temp_code_ids:
                    redis_key = f"send_orders_ds_limit_{payment_id}"
                    cancel_key = f"cancel_send_orders_limit_{payment_id}"

                    # Check if the cancellation key exists in Redis
                    if bool(rds.exists(cancel_key)):  # 确保存在性检查的返回值是布尔值
                        logger.info(f"发现手工删除的订单，跳过插入临时码，取消键: {cancel_key}")
                    else:
                        logger.info(f"正在插入数据到 Redis 键: {redis_key}")
                        try:
                            rds.set(redis_key, payment_id)
                            logger.info(f"成功插入数据到 Redis 键: {redis_key}，数据: {payment_id}")
                        except Exception as e:
                            logger.error(f"写入 Redis 时出错: {e}")
                else:
                    entry['failure_type'] = 0  # 默认值

                # 打印 Payment ID 和相关信息
                logging.info(f"Payment ID: {payment_id}, Fail Count: {entry['fail_count']}, Max Consecutive Failures: {entry['max_consecutive_failures']}, Failure Type: {entry['failure_type']}")

            # 进行批量人工锁定
            batch_size = 1000
            logging.info(f"开始批量人工锁定，待处理的 payment_id 总数: {len(fail_ids)}，批量大小: {batch_size}")

            for b in range(0, len(fail_ids), batch_size):
                batch_ids = fail_ids[b:b + batch_size]
                str_batch_ids = [str(i) for i in batch_ids]

                logging.info(f"当前批次范围: {b} - {b + batch_size - 1}，批量大小: {len(batch_ids)}")
                logging.info(f"当前批次待锁定的 payment_id: {', '.join(str_batch_ids)}")

                # 生成 SQL 语句
                sql = "UPDATE payment SET manual_status=1 WHERE id IN ({ids})".format(ids=','.join(str(d) for d in batch_ids))
                
                # 打印 SQL 语句
                logging.info(f"执行 SQL 语句: {sql}")

                try:
                    cur.execute(sql)
                    connection.commit()
                    logging.info(f"成功锁定 {len(batch_ids)} 个 payment_id")
                except Exception as e:
                    logging.error(f"执行 SQL 语句时出错: {e}")
                    connection.rollback()  # 出错时回滚事务，避免部分更新

            if fail_payments:
                # 按partner_id分组，每个partner_id的payment_id
                grouped_payments = defaultdict(list)
                for entry in fail_payments:
                    grouped_payments[entry['partner_id']].append(entry['payment_id'])



                # 创建消息
                messages = []
                # 遍历每个partner_id和对应的payment_ids
                for partner_id, payment_ids in grouped_payments.items():
                    payment_ids_str = ','.join(map(str, payment_ids))
                    content = f"UPI{payment_ids_str} has been suspended for trading 2 times consecutively! The UPI has been locked! Your UPI may have been locked by the authorities, please check!"
                    messages.append({'to_id': partner_id, 'content': content})

                create_message(rds, connection, cur, messages)

            logging.info(datetime.datetime.now())
        except Exception as e:
            logging.exception('剔除异常码异常:' + str(e))
            connection.rollback()
        finally:
            connection.close()

def create_message(redis_client, connection, cur, messages):
    """
    创建新消息
    :param redis_client: Redis客户端
    :param connection: 数据库连接
    :param cur: 数据库游标
    :param messages: 消息集合，每条消息包含to_id和content
    :return: 消息ID列表
    """
    if not messages:
        return []

    try:
        subject = "系统通知"
        msg_type = 2
        sql = """
            INSERT INTO message (from_id, to_id, type, subject, content, send_time, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        
        # 批量插入的最大数量
        batch_size = 500
        message_ids = []

        for i in range(0, len(messages), batch_size):
            batch_messages = messages[i:i + batch_size]
            values = [
                (1, msg['to_id'], msg_type, subject, msg['content'], datetime.datetime.now(), 2)
                for msg in batch_messages
            ]

            # 执行批量插入
            cur.executemany(sql, values)
            connection.commit()

            # 获取插入的消息ID
            message_ids.extend(cur.lastrowid - len(batch_messages) + j + 1 for j in range(len(batch_messages)))

            # 发送通知
            for msg in batch_messages:
                channel_name = f'user_channel_{msg["to_id"]}'
                notification_data = {
                    'id': message_ids[-1],  # 使用最后插入的消息ID
                    'from_id': 1,
                    'to_id': msg['to_id'],
                    'type': msg_type,
                    'subject': subject,
                    'content': msg['content'],
                    'send_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                redis_client.publish(channel_name, json.dumps({
                    'type': 'new_message',
                    'data': notification_data
                }))

        # 清除用户消息缓存
        for msg in messages:
            pattern = f"user_messages:{msg['to_id']}:*"
            keys = redis_client.keys(pattern)
            if keys:
                redis_client.delete(*keys)

        return message_ids

    except Exception as e:
        logging.exception(e)
        connection.rollback()
        return []

if __name__ == '__main__':
    # 按成功率分等级，按不同等级设定权重来派单
    # main()
    # 按最大限度的剔除出死码和异常码来派单
    main2()
