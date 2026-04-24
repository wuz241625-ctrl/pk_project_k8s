import pymysql
from pymysql import MySQLError
import logging
from logging.handlers import TimedRotatingFileHandler
import sys
import io
import os
import time
from datetime import datetime, timedelta
# 当前脚本目录
# current_dir = os.path.dirname(os.path.abspath(__file__))
# sys.path.append(os.path.join(current_dir, '..'))
from config import get_config

from decimal import Decimal
from datetime import datetime
# 日志配置
LOG_FILE = "partner_summary.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 设置文件处理器
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
fh.stream = io.open(LOG_FILE, 'a', encoding='utf-8')  # 设置日志文件编码为 UTF-8
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)

# 设置控制台输出
ch = logging.StreamHandler(sys.stdout)  # 将日志输出到标准输出（控制台）
ch.setLevel(logging.INFO)  # 可以根据需要设置日志级别
ch.setFormatter(formatter)  # 使用相同的格式化器
logger.addHandler(ch)
# 主函数
def main():
    try:
        logger.info("初始化 MySQL 连接...")
        conf = get_config()
        connection = pymysql.connect(
            host=conf.get('mysql_host', 'localhost'),
            port=conf.get('port', 3306),
            user=conf['mysql_user'],
            password=conf['mysql_password'],
            db=conf['mysql_database'],
            charset=conf.get('charset', 'utf8'),
            autocommit=conf.get('autocommit', False),
            cursorclass=pymysql.cursors.DictCursor
        )
        # 执行支付数据处理
        try:
            logger.info("查询 sys_settings 表 的 value...")
            sql = "SELECT value FROM sys_settings WHERE name = 'partner_statics' LIMIT 1"
            partner_ids_str = ''
            with connection.cursor() as cursor:
                cursor.execute(sql)
                result = cursor.fetchone()
                if result:
                    partner_ids_str = result['value']
                    logger.info(f"获取 partner_id: {partner_ids_str}")
            # 将字符串按逗号分割并去掉空格
            # partner_ids_array = [partner_id.strip() for partner_id in partner_ids_str.split(',')]
            # 将字符串按逗号分割并去掉空格
            partner_ids_array = [
                partner_id.strip() 
                for partner_id in partner_ids_str.split(',')
                if partner_id.strip() 
            ]

            # 检查是否有需要统计的合作商
            if not partner_ids_array:
                logger.info("sys_settings 中 partner_statics 值为空或查询失败，终止统计。")
                return # 安全退出主函数

            date_param = datetime.now().strftime("%Y-%m-%d")
            # 当前日期
            current_date = datetime.now()
            # 前一天
            previous_date = current_date - timedelta(days=1)
            # 格式化为 "YYYY-MM-DD"
            date_param = previous_date.strftime("%Y-%m-%d")
            # date_param = '2024-12-10'
            logger.info(f"获取 当前时间: {date_param}")
            # 假设 partner_ids_array 是包含多个 partner_id 的数组
            # partner_ids_array = [21766,31266,39469]
            for partner_id in partner_ids_array:
                with connection.cursor() as cursor:
                    logger.info(f"获取 partner_id {partner_id} 的所有下属...") 
                    sql = f"""
                    SELECT child FROM partner_tree where parent=%s
                    """
                    cursor.execute(sql, partner_id)
                    partner_ids = [str(row['child']) for row in cursor.fetchall()]
                    # logger.info(f"partner_id {partner_id} 的下属: {partner_ids}")
                    if not partner_ids:
                        continue
                
                # # 示例查询支付数据
                placeholders = ','.join(['%s'] * len(partner_ids))
                query_payout = f"""
                SELECT COUNT(DISTINCT partner_id) AS payoutCount, COALESCE(SUM(amount), 0) AS payoutSum
                FROM orders_df
                WHERE `status` IN (3, 4) AND partner_id IN ({placeholders}) AND DATE(time_updated) = %s;
                """
                with connection.cursor() as cursor:
                    cursor.execute(query_payout, partner_ids + [date_param])
                    # payoutCount, payoutSum = cursor.fetchone() if cursor.rowcount > 0 else (0, 0.0)
                    # 如果没有数据返回，设置默认值
                    result = cursor.fetchone()
                    # 打印查询结果
                    logger.info(f"result==payout==={result}")
                    # 提取 payoutCount 和 payoutSum
                    payoutCount = result.get('payoutCount', 0)  # 如果没有值，默认为 0
                    payoutSum = result.get('payoutSum', Decimal('0.0'))  # 如果没有值，默认为 0.0
                    # 正确输出日志
                    logger.info(f"支付数据: payoutCount={payoutCount}, payoutSum={payoutSum}")

                query_usdt = f"""
                SELECT COUNT(DISTINCT user_id) AS usdtCount, COALESCE(SUM(total_amount), 0) AS usdtSum
                FROM usdt_deposit_orders
                WHERE `status` IN (2) AND user_id IN ({placeholders}) AND DATE(updated_at) = %s;
                """
                    
                with connection.cursor() as cursor:
                    cursor.execute(query_usdt, partner_ids + [date_param])
                    result = cursor.fetchone()
                    # 打印查询结果
                    logger.info(f"result===usdt=={result}")
                    # 提取 payoutCount 和 payoutSum
                    usdtCount = result.get('usdtCount', 0)  # 如果没有值，默认为 0
                    usdtSum = result.get('usdtSum', Decimal('0.0'))  # 如果没有值，默认为 0.0
                    logger.info(f"partner_id {partner_id} 的 USDT 数据: {usdtCount}, {usdtSum}")

                query_combined = f"""
                SELECT partner_id, SUM(amount) AS total_amount
                FROM (
                    SELECT partner_id, amount FROM orders_df
                    WHERE `status` IN (3, 4) AND partner_id IN ({placeholders}) AND DATE(time_updated) = %s
                    UNION
                    SELECT user_id AS partner_id, total_amount AS amount FROM usdt_deposit_orders
                    WHERE `status` IN (2) AND user_id IN ({placeholders}) AND DATE(updated_at) = %s
                ) AS combined
                GROUP BY partner_id;
                """
                with connection.cursor() as cursor:
                    cursor.execute(query_combined, partner_ids + [date_param] + partner_ids + [date_param])
                    combined_results = cursor.fetchall()

                    distinct_partner_count = len(combined_results)
                    # total_combined_sum = sum(row[1] for row in combined_results)
                    # total_combined_sum = payoutSum + usdtSum
                    total_combined_sum = payoutSum + Decimal(usdtSum)

                    logger.info(f"partner_id {partner_id} 的合并数据: {distinct_partner_count}, {total_combined_sum}")

                # 插入数据到数据库
                sql = "SELECT name FROM partner WHERE id = %s LIMIT 1"
                with connection.cursor() as cursor:
                    cursor.execute(sql, ({partner_id},))
                    result = cursor.fetchone()
                    if result:
                        partner_name = result['name']
                        logger.info(f"获取 partner_id的名称: {partner_name}")
                # 确保数据正确处理
                data_to_insert = [(partner_id, date_param, partner_name, payoutCount, payoutSum, usdtCount, usdtSum, distinct_partner_count, total_combined_sum)]

                # 确保所有金额字段都用 Decimal 类型处理
                try:
                    with connection.cursor() as cursor:
                        # 检查记录是否存在
                        check_query = """
                            SELECT COUNT(*) AS count 
                            FROM partner_summary 
                            WHERE partner_id = %s AND formatted_date = %s
                        """
                        cursor.execute(check_query, (partner_id, date_param))
                        result = cursor.fetchone()

                        if result['count'] > 0:
                            # 执行更新
                            update_query = """
                                UPDATE partner_summary 
                                SET name = %s, 
                                    payoutCount = %s, payoutSum = %s,
                                    usdtCount = %s, usdtSum = %s,
                                    count = %s, sum = %s
                                WHERE partner_id = %s AND formatted_date = %s
                            """
                            logger.info(f"{partner_id}: 执行更新")
                            cursor.execute(update_query, (partner_name, payoutCount, payoutSum, usdtCount, usdtSum, distinct_partner_count, total_combined_sum, partner_id, date_param))
                        else:
                            # 执行插入
                            insert_query = """
                                INSERT INTO partner_summary 
                                (partner_id, formatted_date, name, payoutCount, payoutSum, usdtCount, usdtSum, count, sum)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """
                            logger.info(f"{partner_id}: 执行插入")
                            cursor.execute(insert_query, (partner_id, date_param, partner_name, payoutCount, payoutSum, usdtCount, usdtSum, distinct_partner_count, total_combined_sum))
                        
                        # 提交事务
                        connection.commit()

                except Exception as e:
                    print("An error occurred:", e)
                    connection.rollback()
        except Exception as e:
            logger.exception(f"处理时发生异常: {e}")

    except MySQLError as e:
        logger.exception(f"MySQL 连接错误: {e}")
    except Exception as e:
        logger.exception(f"主函数运行出错: {e}")

if __name__ == "__main__":
    main()