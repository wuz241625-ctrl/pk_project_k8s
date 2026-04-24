"""
redis key 常量
"""
class RedisKeys:
    # 存储连接到 websocket 的客户端信息
    REDIS_WS_CLIENTS = "websocket:connected_clients"
