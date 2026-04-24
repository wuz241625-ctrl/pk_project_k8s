import argparse
import asyncio

from redis import asyncio as redis

from config import get_config


PATTERNS = (
    "pre_login_easypaisa_*",
    "login_on_easypaisa_*",
)


async def collect_keys(redis_client):
    keys = []
    for pattern in PATTERNS:
        async for key in redis_client.scan_iter(match=pattern, count=200):
            keys.append(key)
    return keys


async def main(execute: bool):
    conf = get_config()
    redis_client = redis.from_url(
        f"redis://{conf['redis_host']}",
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        keys = await collect_keys(redis_client)
        unique_keys = sorted(set(keys))
        print(f"matched_keys={len(unique_keys)}")
        for key in unique_keys:
            print(key)

        if execute and unique_keys:
            deleted = await redis_client.delete(*unique_keys)
            print(f"deleted_keys={deleted}")
        elif execute:
            print("deleted_keys=0")
        else:
            print("dry_run=true")
    finally:
        await redis_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flush EasyPaisa pre-login sessions and login locks.")
    parser.add_argument("--execute", action="store_true", help="Actually delete matched keys.")
    args = parser.parse_args()
    asyncio.run(main(args.execute))
