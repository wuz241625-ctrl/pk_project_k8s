import datetime
import json

import tornado

from application.base import BaseHandler

TABLE = 'sys_operation_log'
COLUMNS = ['id', 'uid', 'module', 'event_type', 'biz_id', 'utype', 'user_ip', 'request_path', 'event_desc', 'event_content', 'event_result', 'create_time']

class UserType(object):
    ADMIN = 'admin'

class EventType:
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    READ = 'read'
    DOWNLOAD = 'download'

class EventResult:
    FAIL = 'fail'
    SUCCESS = 'success'

def class_to_json(obj):
    keys = dir(obj)
    o = {}
    for key in keys:
        if not key.startswith('__'):
            o[key] = getattr(obj, key)
    return o

# 日志类
class OperationLog:
    def __init__(self, uid, module, event_type):
        self.uid = uid
        self.module = module
        self.event_type = event_type
        self.create_time = datetime.datetime.now()
    biz_id = None
    utype = None
    user_ip = None
    request_path = None
    event_desc = None
    event_content = None
    event_result = None

class IOperationLog(BaseHandler):
    query_keys = ['create_time', 'module', 'event_type', 'uid']
    @tornado.web.authenticated
    async def get(self):
        query = {}
        for key in self.query_keys:
            value = None
            if key == 'create_time':
                value = self.get_arguments(f'{key}[]')
            else:
                value = self.get_argument(key, None)
            if not value is None:
                query[key] = value
        self.logger.info(f'{query}')
        size = int(self.get_argument('size', 10))
        offset = (int(self.get_argument('page', 1))-1) * size
        limit_sql = f'LIMIT {offset},{size}'
        select = []
        conditions = '1=1 '
        values = []

        create_time_key = 'create_time'
        if len(query[create_time_key]):
            _, create_time_between = await self.split_between_condition(query, create_time_key)
            bt_key, bt_start, bt_end = await self.dict_to_between(create_time_between)
            conditions += f'AND a.{create_time_key} BETWEEN %s AND %s '
            values.append(bt_start)
            values.append(bt_end)

        for key in query:
            value = query[key]
            if not value is None and value:
                conditions += f'AND a.{key}=%s '
                values.append(value)
        for key in COLUMNS:
            select.append(f'a.{key}')

        select_sql = f'SELECT {",".join(select)}, b.name AS user_name'
        sql = f'FROM {TABLE} a LEFT JOIN admin b ON a.uid=b.id WHERE {conditions} ORDER BY a.id DESC'

        result = await self.query(f'{select_sql} {sql} {limit_sql}', *values)
        total = await self.query(f'SELECT COUNT(*) AS total {sql}', *values)
        data = {
            'list': result,
            'total': total[0].get('total')
        }
        return await self.json_response(dict(code=20000, data=data, msg='操作成功'))