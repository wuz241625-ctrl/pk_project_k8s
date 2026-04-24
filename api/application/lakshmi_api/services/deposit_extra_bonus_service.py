from application.lakshmi_api.models.sys_info import SysInfo

import global_resources


class DepositExtraBonusService:
    def __init__(self):
        with global_resources.db_orm.sessionmaker() as session:
            self.config = session.query(SysInfo).with_entities(SysInfo.deposit_order_extra_bonus).first()[0]

    def extra_bonus(self, amount):
        extra_bonus = None
        for i in range(1, 7):
            if (self.config.get(f'isOpen{i}', 0) == 1 and
                    self.config.get(f'rangemin{i}', 0) <= amount <= self.config.get(f'rangemax{i}', 0)):
                extra_bonus = self.config.get(f'disprice{i}', None)
                break
        return extra_bonus
