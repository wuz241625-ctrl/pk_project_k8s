"""同步 worker 的 MySQL 连接入口。

Web API 使用 Tornado/aiomysql 连接池；jobs 是独立同步进程，不能直接复用
Application.db。同步 worker 统一通过这里持有并复用连接，避免业务方法里散落
`pymysql.connect`。
"""
import logging

import pymysql

logger = logging.getLogger(__name__)


class DBConnection:
    """持有一个可自动重连的 PyMySQL 连接，供同步 worker 复用。"""

    def __init__(self, conf: dict):
        self._conf = conf
        self._conn = None

    def _connect(self):
        self._conn = pymysql.connect(
            host=self._conf['mysql_host'],
            user=self._conf['mysql_user'],
            password=self._conf['mysql_password'],
            db=self._conf['mysql_database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
        )
        return self._conn

    def ensure_connected(self):
        if self._conn is None or not self._conn.open:
            return self._connect()
        try:
            self._conn.ping(reconnect=True)
        except Exception:
            logger.warning("MySQL 连接 ping 失败，重新连接", exc_info=True)
            return self._connect()
        return self._conn

    @property
    def connection(self):
        return self.ensure_connected()

    def fetch_rows(self, sql, params=None):
        conn = self.ensure_connected()
        with conn.cursor() as cur:
            try:
                cur.execute(sql, params)
                return cur.fetchall()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.commit()

    def execute(self, sql, params=None):
        conn = self.ensure_connected()
        with conn.cursor() as cur:
            try:
                affected = cur.execute(sql, params)
                conn.commit()
                return affected
            except Exception:
                conn.rollback()
                raise
