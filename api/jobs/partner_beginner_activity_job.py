import logging
import os
import random
import sys
import time
import uuid
from datetime import datetime
from decimal import Decimal
from logging.handlers import TimedRotatingFileHandler

import redis
from sqlalchemy import create_engine, text, URL
from sqlalchemy.orm import sessionmaker

# 将项目主目录添加到系统路径
parent_directory = os.path.dirname(__file__)
grandparent_directory = os.path.dirname(parent_directory)
sys.path.append(grandparent_directory)
from config import get_config

"""
每10分钟，执行一次新手活动任务检查及奖励发放
0/10 * * * * python partner_beginner_activity_job.py
"""

# 配置日志
LOG_FILE = "partner_beginner_activity_job.log"
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15, encoding='utf-8')
formatter = logging.Formatter(format_str, datefmt)
handler.setFormatter(formatter)
logger.addHandler(handler)

# 读取配置
conf = get_config()

# job任务锁的键名
partner_beginner_activity_job_lock_key = 'partner_beginner_activity_job_lock'
# 过期时间
partner_beginner_activity_job_lock_expire = 120

class BeginnerActivityReward:
    def __init__(self):
        # 数据库配置
        self.engine = create_engine(URL(
                drivername='mysql+pymysql',
                username=conf['mysql_user'],
                password=conf['mysql_password'],
                port=3306,
                host=conf['mysql_host'],
                database=conf['mysql_database'],
                query={'charset': 'utf8'}
            ))
        self.Session = sessionmaker(bind=self.engine)
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    def check_redis_connection(self):
        try:
            redis_response = self.redis.ping()
            if not redis_response:
                logger.info(f"partner_beginner_activity_job.py; Redis服务未能ping通,3秒后重新连接")
                self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        except Exception as e:
            logger.info(f"partner_beginner_activity_job.py; Redis 连接失败,3秒后重试: {e}")
            time.sleep(3)
            self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.check_redis_connection()  # 递归尝试，不恢复连接不进行下一步

    def acquire_lock(self):
        """尝试获取锁"""
        lock_value = str(uuid.uuid4())  # 使用 UUID 作为锁的值，以确保唯一性
        # 设置锁，NX 表示仅当键不存在时才设置，PX 表示锁的过期时间（毫秒）
        if self.redis.set(partner_beginner_activity_job_lock_key, lock_value, nx=True, px=partner_beginner_activity_job_lock_expire * 1000):
            return lock_value  # 获取锁成功，返回锁的值用于后续释放锁
        else:
            return None  # 获取锁失败

    def release_lock(self, lock_value):
        """释放锁"""
        # 使用 Lua 脚本确保释放锁的操作是原子的
        # 只有当锁的值与传入的 lock_value 相同时，才删除锁
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(lua_script, 1, partner_beginner_activity_job_lock_key, lock_value)

    # 处理保存符合新手活动的新码商
    def process_create_task_progress(self):
        logger.info(f"开始处理参与新手活动的新码商")
        """处理新手奖励"""
        try:
            session = self.Session()
            
            # 1. 查询有效的新手活动及其奖励设置
            active_prize = self._get_active_prize_with_detail(session)
            if not active_prize:
                logger.info("没有进行中的新手活动")
                return

            # 2. 查询符合条件的新注册码商
            new_partners = self._get_eligible_partners_new(session, active_prize)
            if not new_partners:
                logger.info("没有符合条件的新注册码商")
                return

            # 处理每个符合条件的码商
            for partner in new_partners:
                self._create_task_progress(session, active_prize.id, partner)

            session.commit()
            logger.info("奖励处理完成")

        except Exception as e:
            logger.error(f"处理奖励时发生错误: {str(e)}")
            session.rollback()
        finally:
            session.close()

    # 处理保存符合新手活动未完成任务的码商
    def process_rewards(self):
        logger.info(f"开始处理已经参与新手活动但未完成任务码商")
        """处理新手奖励"""
        try:
            session = self.Session()

            # 1. 查询有效的新手活动及其奖励设置
            active_prize = self._get_active_prize_with_detail(session)
            if not active_prize:
                logger.info("没有进行中的新手活动")
                return

            # 2. 查询符合条件的未发放奖励的码商
            not_awarded_partners = self._get_eligible_partners_not_awarded(session, active_prize)
            if not not_awarded_partners:
                logger.info("没有符合条件的待发放奖励的码商")
                return
            logger.info(f"查询到符合条件的未发放奖励的码商,  {len(not_awarded_partners)} 个")
            # 处理每个符合条件的码商
            for partner in not_awarded_partners:
                logger.info(f"处理未发放奖励的码商,  partner.id: {partner.id}")
                self._process_partner(session, partner, active_prize)

            session.commit()
            logger.info("奖励处理完成")

        except Exception as e:
            logger.error(f"处理奖励时发生错误: {str(e)}")
            session.rollback()
        finally:
            session.close()

    """查询有效的新手活动及其奖励设置"""
    def _get_active_prize_with_detail(self, session):
        now = datetime.now()
        sql = """
        SELECT 
            ps.*,
            psd.id as detail_id,
            psd.money as reward_amount,
            psd.ratio as reward_ratio,
            psd.prize_limit_min,
            psd.prize_limit_max
        FROM prize_setting ps
        JOIN prize_setting_detail psd ON ps.id = psd.prize_id
        WHERE ps.type = 3 and  ps.begin_at <= :now and ps.end_at > :now
        AND ps.status = 1
        LIMIT 1
        """
        return session.execute(text(sql), {"now": now}).first()

    def _get_eligible_partners_new(self, session, prize):
        """查询符合条件的新注册码商"""
        sql = """
        SELECT p.* FROM partner p 
        LEFT JOIN prize_partner_beginner_tutorial_task_progress pt 
        ON p.id = pt.partner_id AND pt.prize_id = :prize_id 
        WHERE p.status = 1 and p.time_create >= :prize_begin_at and  p.time_create < :prize_end_at
        AND pt.id IS NULL
        """
        text_sql = text(sql)
        return session.execute(text_sql, {
            "prize_id": prize.id,
            "prize_begin_at": prize.begin_at,
            "prize_end_at": prize.end_at
        }).fetchall()

    """查询符合条件的未发放奖励的码商"""
    def _get_eligible_partners_not_awarded(self, session, prize):
        sql = """
        SELECT p.* FROM partner p 
        LEFT JOIN prize_partner_beginner_tutorial_task_progress pt 
        ON p.id = pt.partner_id AND pt.prize_id = :prize_id
        WHERE p.status = 1 
        AND pt.is_awarded = 0
        """
        text_sql = text(sql)
        return session.execute(text_sql, {
            "prize_id": prize.id
        }).fetchall()

    """
    创建任务进度
    任务类型;1=register(注册),2=watch_tutorial_videos(观看引导视频),3=bind_upi(绑定UPI),4=order_success(成功代付订单)
    """
    def _create_task_progress(self, session, prize_id, partner):
        """创建任务进度记录"""
        now = datetime.now()

        # 查询顶商id
        top_parent_id = self.get_top_level_id(session, partner.id)
        sql = """
                            INSERT INTO prize_partner_beginner_tutorial_task_progress 
                            (prize_id, partner_id, top_parent_id, pid, is_finished, is_awarded, time_register, create_at)
                            VALUES (:prize_id, :partner_id, :top_parent_id, :pid, 0, 0, :time_register, :now)
                            """
        condition = {
            "prize_id": prize_id,
            "partner_id": partner.id,
            "top_parent_id": top_parent_id,
            "pid": partner.pid,
            "time_register": partner.time_create,
            "now": now
        }
        session.execute(text(sql), condition)

        return self._get_task_progress(session, prize_id, partner)

    def _create_prize_log(self, session,partner, prize):
        """创建任务进度记录"""
        now = datetime.now()
        sql = """
             INSERT INTO prize_earn_log 
            (user_id, user_name, prize_id, prize_detail_id, prize_title, money, remark, created_at)
            VALUES (:user_id,:user_name, :prize_id, :prize_detail_id, :prize_title, :money, :remark, :now)
            """
        reward_amount = Decimal(str(prize.reward_amount))
        condition = {
            "user_id": partner.id,
            "user_name": partner.name,
            "prize_id": prize.id,
            "prize_detail_id": prize.detail_id,
            "prize_title": prize.title,
            "money": reward_amount,
            "remark": f'完成新手活动，奖励{reward_amount}',
            "now": now
        }
        session.execute(text(sql), condition)

    """查询码商"""
    def _get_partner(self, session, partner):
        return session.execute(
            text("SELECT * FROM partner WHERE partner_id = :partner_id"),
            {"partner_id": partner.id}
        ).first()

    """查询任务进度"""
    def _get_task_progress(self, session, prize_id, partner):
        return session.execute(
            text("SELECT * FROM prize_partner_beginner_tutorial_task_progress WHERE prize_id = :prize_id AND partner_id = :partner_id"),
            {"prize_id": prize_id, "partner_id": partner.id}
        ).first()

    """查询任务列表"""
    def _get_task_list(self, session, prize_id):
        return session.execute(
            text("SELECT * FROM prize_setting_partner_beginner_tutorial_task WHERE prize_id = :prize_id AND status_enable = 1"),
            {"prize_id": prize_id}
        ).all()

    def _check_payment_binding(self, session, prize, partner_id):
        """检查是否绑定了银行卡"""
        sql = """
        SELECT COUNT(1) as count, min(payment.time_create) as time_create 
        FROM payment 
        inner join bank_type on bank_type.id = payment.bank_type and bank_type.type = 1
        WHERE partner_id = :partner_id and ((payment.upi is not null and payment.upi != '') or payment.status = 1)
        """
        result = session.execute(text(sql),
             {
                 "partner_id": partner_id
             }
        ).first()
        if result.count > 0:
            return result
        else:
            return None

    def _check_successful_orders(self, session, partner_id, begin_at, end_at):
        """检查是否有成功订单"""
        sql = """
        SELECT COUNT(1) as count, min(orders_df.time_create) as time_create 
        FROM orders_df 
        WHERE partner_id = :partner_id 
        AND status = 4 
        """
        result = session.execute(text(sql), {
            "partner_id": partner_id
        }).first()

        if result.count > 0:
            return result
        else:
            return None

    def _update_task_progress(self, session, progress_id, updates):
        """更新任务进度"""
        set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
        sql = f"""
        UPDATE prize_partner_beginner_tutorial_task_progress 
        SET {set_clause}
        WHERE id = :progress_id
        """
        updates["progress_id"] = progress_id
        session.execute(text(sql), updates)

    def _create_balance_record(self, session, partner_id, amount):
        """创建余额变动记录"""
        # 获取当前余额
        sql = "SELECT balance FROM partner WHERE id = :partner_id"
        current_balance = session.execute(text(sql), {"partner_id": partner_id}).first().balance
        
        # 插入余额变动记录
        sql = """
        INSERT INTO balance_record 
        (code, change_before, amount, change_after, record_type, user_type, user_id, remark, time_create)
        VALUES (:code, :change_before, :amount, :change_after, 6, 0, :user_id, :remark, :time_create)
        """
        session.execute(text(sql), {
            "code": str(uuid.uuid4()),
            "change_before": current_balance,
            "amount": amount,
            "change_after": current_balance + amount,
            "user_id": partner_id,
            "remark": "新手教程奖励",
            "time_create": datetime.now()
        })

    """
    创建编码
    """
    def create_code(self, PRE='R'):
        return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))

    # 余额变动
    def _change_balance(self, session, table, user_id, amount, code, record_type, remark=None):
        sql_update = 'update {table} set balance=balance + :amount where id = :id'.format(table=table)
        sql_select = """select balance{other} from {table} where id = :id""".format(
            table=table,
            other=',vip' if table == 'partner' else '')
        sql_insert = """
            insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark) 
            value 
            (:code,:user_type,:user_id,:change_before,:amount,:change_after,:record_type,:remark)
        """
        sql_select_vip = """select vip,conditions from vip"""
        sql_update_vip = """update partner set vip=:vip where id = :id"""

        result_1 = session.execute(text(sql_select), {"id": user_id}).first()

        if not result_1:
            # session.rollback()
            return False
        _before = result_1.balance

        logger.info('更改金额{sql}, values: {values}'.format(sql=text(sql_update), values= {"amount": amount, "id": user_id}))
        result_2 = session.execute(text(sql_update), {"amount": amount, "id": user_id})
        if not result_2:
            return False
        user =  session.execute(text(sql_select), {"id": user_id}).first()
        if not user:
            # session.rollback()
            return False
        partnerBalance = 0

        _after = user.balance
        if Decimal(_after) < partnerBalance:
            # session.rollback()
            return False
        user_type = 0 if table == 'partner' else 1

        sql_insert_condition = {
            "code": code,
            "user_type": user_type,
            "user_id": user_id,
            "change_before": _before,
            "amount": amount,
            "change_after": _after,
            "record_type": record_type,
            "remark": remark
        }

        logger.info(f"保存交易记录的sql: {text(sql_insert)}, 条件：{sql_insert_condition}")
        result_4 = session.execute(text(sql_insert), sql_insert_condition)

        if not result_4:
            # session.rollback()
            return False

        # vip
        if table == 'partner' and amount > Decimal(0):
            _vip = 0
            # _deposit = 0
            result_5 = session.execute(text(sql_select_vip)).all()
            if not result_5:
                # session.rollback()
                return False
            for i in result_5:
                if _after >= i.conditions:
                    _vip = i.vip

            if int(_vip) > user.vip:
                if int(_vip) > user.vip:  # 余额够升级时
                    result_6 = session.execute(text(sql_update_vip), {"vip":_vip, "id": user_id})
                    if not result_6:
                        # session.rollback()
                        logger.warning('{user_id}改变VIP失败'.format(user_id=user_id))
                        return False
        return True

    """发放奖励"""
    def _award_prize(self, session, partner_id, reward_amount):
        logger.info(f"为码商{partner_id}增加余额{reward_amount}")
        # 更新码商余额
        sql = """
        UPDATE partner 
        SET balance = balance + :amount 
        WHERE id = :partner_id
        """
        session.execute(text(sql), {
            "partner_id": partner_id,
            "amount": reward_amount
        })
        
        # 创建余额变动记录
        self._create_balance_record(session, partner_id, reward_amount)

    """处理参与活动进行中的码商"""
    def _process_partner(self, session, partner, prize):
        """处理单个码商的奖励"""
        try:

            task_list = self._get_task_list(session, prize.id)
            if task_list is None or len(task_list) == 0:
                return

            # 查询任务进度
            progress = self._get_task_progress(session, prize.id, partner)
            updates = {}
            # 已完成任务的总数
            number_of_finished = 0

            for task in task_list:
                logger.info(f""" 任务: {task} """)
                match task.type:
                    case 1:
                        # 检查是否已设置安全码
                        if partner.hash_trade is not None:
                            updates["time_set_trade_hash"] = partner.time_update
                            logger.info(f"查询到码商 {partner.id}, 安全码更新时间为: {partner.time_update}")
                            number_of_finished = number_of_finished + 1
                        continue
                    case 2:
                        number_of_finished = number_of_finished + 1
                        continue
                    case 3:
                        # 检查银行卡绑定
                        result_1 = self._check_payment_binding(session, prize, partner.id)
                        if result_1 and result_1.count > 0:
                            updates["time_bind_upi"] = result_1.time_create
                            logger.info(f"查询到码商 {partner.id}, upi绑定时间: {result_1.time_create}")
                            number_of_finished = number_of_finished + 1
                        continue
                    case 4:
                        # 检查成功订单
                        result_2 = self._check_successful_orders(session, partner.id, prize.begin_at, prize.end_at)
                        if result_2 and result_2.count > 0:
                            updates["time_order_success"] = result_2.time_create
                            logger.info(f"查询到码商 {partner.id}, 付款订单时间: {result_2.time_create}")
                            number_of_finished = number_of_finished + 1
                        continue
                    case 5:
                        continue
                    case 6:
                        continue
                    case _:
                        break
                logger.info(f"number_of_finished: {number_of_finished}")

            # 更新进度
            if updates:
                updates["is_finished"] = 1 if number_of_finished == len(task_list) else 0
                self._update_task_progress(session, progress.id, updates)

            # 如果所有任务都完成，发放奖励
            if number_of_finished == len(task_list):
                reward_amount = Decimal(str(prize.reward_amount))
                # self._award_prize(session, partner.id, reward_amount)
                balance_record_code = self.create_code('HD')
                result = self._change_balance(session, 'partner', partner.id, reward_amount, balance_record_code, 7, prize.title)
                if result is None or result == False:
                    raise ValueError("变更码商余额异常")

                # 增加活动中奖记录
                self._create_prize_log(session,partner, prize)
                self._update_task_progress(session, progress.id, {
                    "is_awarded": 1,
                    "prize_amount": reward_amount,
                    "time_awarded": datetime.now()
                })
                logger.info(f"已发放奖励给码商 {partner.id}, 金额: {reward_amount}")

        except Exception as e:
            logger.error(f"处理码商 {partner.id} 时发生错误: {str(e)}")
            raise

    #根据id查询顶级id
    def get_top_level_id(self, session, id):
        if id is None:
            logger.error("传入的pid为None，无法查询顶级id")
            return None

        sql = """
        SELECT parent FROM partner_tree 
        WHERE child = :child 
        ORDER BY distance DESC 
        LIMIT 1
        """
        
        result = session.execute(text(sql), {"child": id}).fetchone()
        
        if result:
            top_level_id = result[0]
            logger.info(f"ID={id} 的顶级 ID 是 {top_level_id}")
            return top_level_id
        else:
            logger.warning(f"未找到 ID={id} 的记录")
            return None
    #根据pid查询顶级id
    # def get_top_level_id_by_cache(self, pid):
    #     if not self.partner_tree_cache:
    #         with self.Session() as session:
    #             sql = "SELECT child, parent, distance FROM partner_tree"
    #             self.partner_tree_cache = {row.child: (row.parent, row.distance) for row in session.execute(text(sql)).fetchall()}

    #     current_pid = pid
    #     while True:
    #         if current_pid not in self.partner_tree_cache:
    #             return None  # 如果没有找到记录，返回None
            
    #         parent_id, distance = self.partner_tree_cache[current_pid]
            
    #         if distance == 0:
    #             return parent_id  # 找到顶级id，返回parent值
            
    #         current_pid = parent_id  # 继续向上查询

if __name__ == "__main__":
    reward_service = BeginnerActivityReward()
    # 检查redis连接
    reward_service.check_redis_connection()

    # 获取锁
    lock_value = reward_service.acquire_lock()
    if lock_value:
        try:
            # 执行业务逻辑
            logger.info(f"{lock_value} 开始任务...")

            # 处理保存符合新手活动的新码商
            reward_service.process_create_task_progress()
            # 处理保存符合新手活动未完成任务的码商
            reward_service.process_rewards()
            # 业务逻辑处理完毕
            logger.info(f"{lock_value} 任务执行完成")
        finally:
            # 释放锁
            reward_service.release_lock(lock_value)
    else:
        # 锁已被其他进程持有，跳过执行
        logger.info(f"{lock_value} 锁由另一个进程持有，跳过执行。")