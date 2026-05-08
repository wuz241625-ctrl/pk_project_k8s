import pymysql
import logging

logger = logging.getLogger(__name__)


class DBConnection:
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
            self._connect()
        else:
            try:
                self._conn.ping(reconnect=True)
            except Exception:
                self._connect()
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
            except Exception as e:
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
            except Exception as e:
                conn.rollback()
                raise
