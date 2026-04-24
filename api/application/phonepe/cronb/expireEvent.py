import asyncio
import redis.asyncio as aioredis  # 注意模块名称

async def listen_for_expire_events():
    print("Connecting to Redis...")

    # 使用 redis-py 创建 Redis 连接
    redis = aioredis.from_url('redis://localhost')

    # 确保成功连接 Redis
    try:
        await redis.ping()
        print("Connected to Redis.")
    except aioredis.RedisError as e:
        print(f"Failed to connect to Redis: {e}")
        return

    # 订阅 keyspace 事件
    print("Subscribing to keyspace events...")
    try:
        pubsub = redis.pubsub()
        await pubsub.psubscribe('__keyevent@0__:expired')
        print("Subscribed to Redis keyspace events.")
    except aioredis.RedisError as e:
        print(f"Failed to subscribe to keyspace events: {e}")
        return

    # 开始监听事件
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                expired_key = message['data'].decode('utf-8')
                print(f"Received expired event for key: {expired_key}")
                if expired_key.startswith('heartbeat:'):
                    payment_id = expired_key.split(':')[1]
                    await handle_expired_heartbeat(payment_id)
            await asyncio.sleep(0.1)  # 防止 CPU 占用过高
    except Exception as e:
        print(f"Error while listening for expire events: {e}")
    finally:
        await redis.close()

async def handle_expired_heartbeat(payment_id):
    print(f"Handling expired heartbeat for payment_id: {payment_id}")
    redis = aioredis.from_url('redis://localhost')
    result_online = await redis.srem('payment_online_ds', payment_id)
    result_active = await redis.lrem('payment_active_1001', 0, payment_id)
    print(f"Removed from payment_online_ds: {result_online}, Removed from payment_active_1001: {result_active}")
    await redis.close()

async def main():
    await listen_for_expire_events()

if __name__ == '__main__':
    asyncio.run(main())
