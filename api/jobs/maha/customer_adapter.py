import requests
import ssl
from urllib3.util.ssl_ import create_urllib3_context
from urllib3.poolmanager import PoolManager

# 创建自定义 SSL 上下文
class CustomAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.ssl_context = kwargs.pop('ssl_context', None)
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        context = self.ssl_context if self.ssl_context else create_urllib3_context(
            ssl_version=ssl.PROTOCOL_TLSv1_2,
            ciphers='DEFAULT:@SECLEVEL=1'
        )
        
        # 添加所有必要的SSL选项
        context.options |= (
            ssl.OP_LEGACY_SERVER_CONNECT |  # 启用旧版重新协商
            ssl.OP_NO_SSLv2 | 
            ssl.OP_NO_SSLv3 |
            ssl.OP_NO_COMPRESSION |
            ssl.OP_CIPHER_SERVER_PREFERENCE
        )
        
        # 禁用证书验证
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        kwargs['ssl_context'] = context
        
        return super().init_poolmanager(*args, **kwargs)
    
    
def create_ssl_context():
    # 创建自定义SSL上下文
    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3
    context.options |= ssl.OP_NO_COMPRESSION
    context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
    context.verify_mode = ssl.CERT_NONE
    context.check_hostname = False
    context.set_ciphers('ALL:@SECLEVEL=0')
    return context