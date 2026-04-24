import logging

import redis

class RedisOrderManager:

    def __init__(self, logger: logging.Logger, redis_client: redis.Redis):
        self.logger = logger
        """
        初始化 Redis 连接。
        """
        self.redis_client = redis_client
        self.paid_ok_orders_df_code = "paid_ok_orders_df_code"  # 存储支付成功的代付订单号的无序集合键名

    def add_paid_ok_order(self, order_code) -> bool:
        """
        将支付成功的订单号添加到无序集合中。
        :param order_code: 订单号
        :return: 添加成功返回 True，否则返回 False
        """
        try:
            self.logger.info(f"redis操作: 向 set: {self.paid_ok_orders_df_code}, 添加 {order_code}")
            return self.redis_client.sadd(self.paid_ok_orders_df_code, order_code) == 1
        except Exception as e:
            self.logger.error(f"添加订单号失败: {e}")
            return False

    def contains_order(self, order_code) -> bool:
        """
        检查无序集合中是否包含指定订单号。
        :param order_code: 订单号
        :return: 包含返回 True，否则返回 False
        """
        try:
            self.logger.info(f"redis操作: 检查 set: {self.paid_ok_orders_df_code}, 是否包含 {order_code}")
            return self.redis_client.sismember(self.paid_ok_orders_df_code, order_code)
        except Exception as e:
            self.logger.error(f"检查订单号失败: {e}")
            return False

    def remove_order(self, order_code) -> bool:
        """
        从无序集合中删除指定订单号。
        :param order_code: 订单号
        :return: 删除成功返回 True，否则返回 False
        """
        try:
            self.logger.info(f"redis操作: 从 set: {self.paid_ok_orders_df_code}, 删除 {order_code}")
            return self.redis_client.srem(self.paid_ok_orders_df_code, order_code) == 1
        except Exception as e:
            self.logger.error(f"删除订单号失败: {e}")
            return False

    def get_all_orders(self):
        """
        获取所有支付成功的订单号。
        :return: 订单号列表
        """
        try:
            self.logger.info(f"redis操作: 读取 set: {self.paid_ok_orders_df_code}")
            return self.redis_client.smembers(self.paid_ok_orders_df_code)
        except Exception as e:
            self.logger.error(f"获取订单号列表失败: {e}")
            return set()
