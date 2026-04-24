from application.lakshmi_api.base import BaseHandler
from application.lakshmi_api.models.sys_info import SysInfo


class AppInformation(BaseHandler):
    async def get(self):
        with self.db_orm.sessionmaker() as session:
            sys_info = session.query(SysInfo).first()

        self.write(sys_info.app_info)
