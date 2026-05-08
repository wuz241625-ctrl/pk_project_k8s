# jobs/easypaisa/common/redis_client.py
import os
import time
import hashlib
import secrets
import redis as redis_lib
import logging
from typing import List

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self, conf: dict):
        self._conf = conf
        self._redis = redis_lib.Redis(
            host=conf['redis_host'], port=int(conf.get('redis_port', 6379)), db=0, encoding='utf-8'
        )

    @property
    def redis(self):
        return self._redis

    def check_connection(self):
        try:
            if not self._redis.ping():
                self._reconnect()
        except Exception:
            time.sleep(2)
            self._reconnect()
            self.check_connection()

    def _reconnect(self):
        self._redis = redis_lib.Redis(
            host=self._conf['redis_host'], port=int(self._conf.get('redis_port', 6379)), db=0, encoding='utf-8'
        )

    def get_lock(self, name: str, resource_id: str, ttl: int = 30):
        busy_key = f'{name}_operate_{resource_id}'
        value = secrets.token_hex(8)
        acquired = self._redis.setnx(busy_key, value)
        if not acquired:
            existing_ttl = self._redis.ttl(busy_key)
            if existing_ttl and int(existing_ttl) > ttl:
                self._redis.delete(busy_key)
            return None
        self._redis.expire(busy_key, ttl)
        return value

    def del_lock(self, name: str, resource_id: str, lock_value: str):
        busy_key = f'{name}_operate_{resource_id}'
        current = self._redis.get(busy_key)
        if current and current.decode() == lock_value:
            self._redis.delete(busy_key)
            return True
        return False

    def get_process_allocated_members(self, members: List[bytes], process_name: str = "easypaisa_monitor") -> List[bytes]:
        if not members:
            return []
        total_processes, current_index = self._get_active_processes_count(process_name)
        if total_processes <= 1:
            return members
        allocated = []
        for member in members:
            member_id = member.decode() if isinstance(member, bytes) else str(member)
            hash_value = int(hashlib.md5(member_id.encode()).hexdigest(), 16)
            if hash_value % total_processes == current_index:
                allocated.append(member)
        return allocated

    @staticmethod
    def _get_active_processes_count(process_name: str):
        try:
            import subprocess
            result = subprocess.run(
                ['pgrep', '-f', process_name], capture_output=True, text=True
            )
            pids = []
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line:
                    try:
                        pids.append(int(line))
                    except ValueError:
                        continue
            pids.sort()
            current_pid = os.getpid()
            total = len(pids)
            index = pids.index(current_pid) if current_pid in pids else 0
            return total, index
        except Exception:
            return 1, 0
