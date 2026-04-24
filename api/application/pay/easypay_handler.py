"""
Easypay SOAP 代收 — 收银台表单提交处理

用户输入手机号后 POST 到此 handler：
1. 校验参数 → 发起 SOAP（后台任务，不阻塞 HTTP 连接）→ 秒回
2. 前端轮询 /status/ds 查订单状态
3. 后台 SOAP 返回成功 → order_success_ds_third 结算 → 订单状态变 3
4. 后台 SOAP 失败 → 订单状态变 -1 → 前端轮询到后显示失败
"""
import re
import asyncio
import logging

from application.base import BaseHandler
from application.pay.easypay_soap import async_initiate_transaction
from .success import order_success_ds_third

logger = logging.getLogger(__name__)


async def _easypay_background_task(handler, code, config, amount, msisdn):
    """后台协程：等待 SOAP 返回并处理结算，不占用 HTTP 连接"""
    lock_key = f'easypay_init_lock_{code}'
    try:
        logger.info(f'[easypay] 后台任务开始, code={code}, msisdn={msisdn}, amount={amount}')
        result = await async_initiate_transaction(
            soap_url=config['pay_url'],
            username=config['key'],
            password=config['key2'],
            order_id=code,
            store_id=config['key3'],
            amount=float(amount),
            mobile_number=msisdn,
            email='customer@easypay.com',
            timeout_seconds=90,
        )

        logger.info(f'[easypay] SOAP 返回, code={code}, response_code={result.get("response_code")}')

        if result.get('success'):
            transaction_id = result.get('transaction_id')
            settle_ok = await order_success_ds_third(handler, code, utr=msisdn)
            if settle_ok is True:
                logger.info(f'[easypay] 订单{code}结算成功')
                if transaction_id:
                    try:
                        async with handler.application.db.acquire() as conn:
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    "UPDATE orders_ds SET trans_id=%s WHERE code=%s AND (trans_id IS NULL OR trans_id='')",
                                    (transaction_id, code))
                                await conn.commit()
                        logger.info(f'[easypay] 订单{code} 写入 trans_id={transaction_id}')
                    except Exception as tid_err:
                        logger.exception(f'[easypay] 订单{code} 写入 trans_id 异常: {tid_err}')
            else:
                logger.error(f'[easypay] 订单{code} SOAP 成功但结算失败: {settle_ok}')
        else:
            error_msg = result.get('error', result.get('response_code', 'unknown'))
            logger.warning(f'[easypay] 订单{code}交易失败或超时: {error_msg}')
            # SOAP 失败 → status=-1，前端轮询 /status/ds 到 status<=0 会显示失败
            try:
                async with handler.application.db.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE orders_ds SET status=-1 WHERE code=%s AND status=1", code)
                        await conn.commit()
                logger.info(f'[easypay] 订单{code}已标记为失败(status=-1)')
            except Exception as db_err:
                logger.exception(f'[easypay] 订单{code}更新失败状态异常: {db_err}')

    except Exception as e:
        logger.exception(f'[easypay] 后台任务异常, code={code}: {e}')
    finally:
        await handler.redis.delete(lock_key)


class EasypayInitiate(BaseHandler):
    async def post(self):
        token = self.get_argument('token', None)
        msisdn = self.get_argument('msisdn', None)

        if not token or not msisdn:
            return self.write({'code': 1, 'message': 'missing token or msisdn'})

        # 后端校验手机号格式
        msisdn = msisdn.strip().replace(' ', '')
        if not re.match(r'^03\d{9}$', msisdn):
            return self.write({'code': 1, 'message': 'invalid mobile number'})

        # 校验 token → 获取订单 code
        code = await self.token_decode(token)
        if code in [10016, 10017]:
            return self.write({'code': 1, 'message': 'token expired or invalid'})

        # Redis 幂等锁，防止同单重复发起 SOAP
        lock_key = f'easypay_init_lock_{code}'
        if not await self.redis.setnx(lock_key, 1):
            self.logger.warning(f'[easypay] 订单{code}重复发起，已有锁')
            return self.write({'code': 1, 'message': 'payment already in progress'})
        await self.redis.expire(lock_key, 120)

        # 查询订单：校验 third_party_name 必须是 easypay 且 status=0（未发起过）
        sql_order = """SELECT code, amount, channel_code, status, merchant_id, third_party_name, otherpay
                       FROM orders_ds
                       WHERE code=%s AND status=0
                       AND third_party_name='easypay'
                       AND time_create > DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                       LIMIT 1"""
        order = await self.query(sql_order, code)
        if not order:
            await self.redis.delete(lock_key)
            self.logger.error(f'[easypay] 订单不存在、已过期、非easypay或已发起: {code}')
            return self.write({'code': 1, 'message': 'order not available'})
        order = order[0]

        # 按订单绑定的 otherpay.id 精确查配置（支持多账号）
        otherpay_id = order.get('otherpay')
        if not otherpay_id:
            await self.redis.delete(lock_key)
            self.logger.error(f'[easypay] 订单{code}未绑定 otherpay 配置')
            return self.write({'code': 1, 'message': 'easypay config not bound'})

        sql_config = """SELECT merchant_id, `key`, key2, key3, pay_url
                        FROM otherpay
                        WHERE id=%s AND status=1
                        LIMIT 1"""
        config = await self.query(sql_config, otherpay_id)
        if not config:
            await self.redis.delete(lock_key)
            self.logger.error(f'[easypay] 未找到启用的 easypay 配置')
            return self.write({'code': 1, 'message': 'easypay config not found'})
        config = config[0]

        self.logger.info(f'[easypay] 发起 MA 交易(后台), code={code}, amount={order["amount"]}')

        # 原子更新 status 0→1，防止并发重复发起
        affected = await self.execute(
            "UPDATE orders_ds SET status=1, utr=%s WHERE code=%s AND status=0", msisdn, code)
        if not affected:
            await self.redis.delete(lock_key)
            self.logger.warning(f'[easypay] 订单{code}状态更新失败，可能已被处理')
            return self.write({'code': 1, 'message': 'order already processing'})

        # 后台任务发起 SOAP，不阻塞 HTTP 连接
        asyncio.create_task(_easypay_background_task(
            self, code, config, order['amount'], msisdn))

        # 秒回，前端转入轮询 /status/ds
        return self.write({'code': 0, 'message': 'payment request sent'})
