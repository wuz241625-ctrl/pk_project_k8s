"""Decimal amount generation and cleanup for collection orders."""

import time
import random
from decimal import Decimal


async def generate_unique_decimal_amount(handler, original_amount, decimal_min, decimal_max, channel_code, order_code, payment_id):
    """
    生成唯一的小数点金额，使用新的 List + Hash 设计方案
    Args:
        handler: 包含 redis 和 logger 的处理器对象
        original_amount: 原始金额
        decimal_min: 最小小数点值
        decimal_max: 最大小数点值
        channel_code: 通道代码
        order_code: 订单号
        payment_id: 收款账户ID
    Returns:
        Decimal: 唯一的小数点金额，失败返回None
    """
    max_attempts = 100  # 最大尝试次数
    order_timeout = 480   # 订单有效期8分钟（比订单超时时间7分钟稍长）
    list_timeout = 600    # List存在时间10分钟（比订单有效期长）

    for attempt in range(max_attempts):
        # 生成随机小数部分
        decimal_part = Decimal(format(random.uniform(decimal_min, decimal_max), '.2f'))
        new_amount = original_amount + decimal_part

        # Redis 键设计
        amount_key = f"decimal_amount:{new_amount:.2f}"           # List 存储 payment_id 队列
        cleanup_key = f"decimal_cleanup:{new_amount:.2f}"         # Hash 存储删除时间控制

        # 检查是否已有相同 payment_id 在队列中
        existing_payment_ids = await handler.redis.lrange(amount_key, 0, -1)
        # 处理字节类型转换，确保类型一致性
        existing_payment_ids_str = [pid.decode() if isinstance(pid, bytes) else str(pid) for pid in existing_payment_ids]
        if str(payment_id) in existing_payment_ids_str:
            handler.logger.warning(f'payment_id {payment_id} 已在金额 {new_amount:.2f} 的队列中，重新生成')
            continue

        try:
            # 原子操作：将 payment_id 添加到队列并设置删除时间
            pipe = handler.redis.pipeline()

            # 1. 将 payment_id 添加到 List 头部
            pipe.lpush(amount_key, payment_id)

            # 2. 设置删除时间戳到 Hash 中
            current_time = time.time()
            expire_time = current_time + order_timeout
            pipe.hset(cleanup_key, payment_id, expire_time)

            # 3. 设置 payment_id 释放时间控制（使用payment_id+金额确保唯一性）
            release_key = f"{payment_id}:{new_amount:.2f}"
            pipe.hset('payment_release_time', release_key, expire_time)

            # 4. 设置 List 的过期时间（比订单有效期长）
            pipe.expire(amount_key, list_timeout)
            pipe.expire(cleanup_key, list_timeout)

            # 执行原子操作
            await pipe.execute()

            handler.logger.info(f'生成唯一小数点金额成功: {new_amount:.2f}, payment_id: {payment_id} (尝试次数: {attempt + 1})')
            handler.logger.info(f'设置过期时间: {expire_time}, 当前时间: {current_time}')
            return new_amount

        except Exception as e:
            handler.logger.error(f'Redis 操作失败: {e}, 重试 (尝试次数: {attempt + 1})')
            continue

    # 超过最大尝试次数，生成失败
    handler.logger.error(f'生成唯一小数点金额失败，超过最大尝试次数 {max_attempts}')
    return None


async def cleanup_decimal_callback_on_success(handler, payment_id, amount, cleanup_reason="成功回调"):
    """
    小数点回调清理函数
    可用于成功回调后清理或超时清理

    Args:
        handler: 包含 redis 和 logger 的处理器对象
        payment_id: 支付ID
        amount: 金额
        cleanup_reason: 清理原因，默认为"成功回调"，可传入"超时清理"等
    """
    try:
        amount_key = f'decimal_amount:{amount:.2f}'
        cleanup_key = f'decimal_cleanup:{amount:.2f}'

        # 从 List 中删除 payment_id
        removed_count = await handler.redis.lrem(amount_key, 1, payment_id)
        if removed_count > 0:
            handler.logger.info(f'{cleanup_reason}清理: 从 {amount_key} 中删除 {payment_id}')

        # 从 Hash 中删除对应记录（使用payment_id+金额作为释放时间控制键）
        await handler.redis.hdel(cleanup_key, payment_id)
        release_key = f"{payment_id}:{amount:.2f}"
        await handler.redis.hdel('payment_release_time', release_key)

        handler.logger.info(f'{cleanup_reason}清理完成: payment_id={payment_id}, amount={amount}')

    except Exception as e:
        handler.logger.exception(f'{cleanup_reason}清理失败: {e}')
