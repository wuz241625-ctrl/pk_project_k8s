"""自动代付运行态读取。

业务最终态放在 MySQL，Redis 只保留锁、缓存和临时信号。
"""
import pymysql


def is_auto_payout_enabled(conf, logger=None, default=True):
    """读取全局自动代付开关。

    `auto_payout_system_status.system_status = running` 表示自动代付 worker 可以处理订单。
    表或记录不存在时沿用历史默认：未配置即开启。
    """
    connection = None
    try:
        connection = pymysql.connect(
            host=conf['mysql_host'],
            user=conf['mysql_user'],
            password=conf['mysql_password'],
            database=conf['mysql_database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT system_status
                FROM auto_payout_system_status
                WHERE id = 1
                LIMIT 1
                """
            )
            row = cur.fetchone()
        if not row:
            return default
        return row.get('system_status') == 'running'
    except Exception as exc:
        if logger:
            logger.warning(f"读取自动代付MySQL开关失败，使用默认值 {default}: {exc}")
        return default
    finally:
        if connection:
            connection.close()
