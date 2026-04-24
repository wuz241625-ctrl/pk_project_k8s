import hashlib
import hmac
import base64
import urllib
from urllib import parse
from decimal import Decimal
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
import re
import time
import random
class SignatureAndVerification(object):
    """签名和验签"""

    @classmethod
    def data_processing(cls, data):
        if "sign" in data:
            del data["sign"]
        dataList = []
        for key in sorted(data):
            if data[key]:
                dataList.append("%s=%s" % (key, data[key]))
        return "&".join(dataList).strip()

    @classmethod
    def data_processing2(cls, data):
        """
        此参数处理中，值为None或空值的只连接key值，不需后接等号
        如： {"transferTime": None, "withdrawAmount": "5.00"}
        转为： "transferTime&withdrawAmount=5.00"
        """
        processed_params = []
        for key, value in data.items():
            if key == 'sign':
                continue
            if value is None or value == '':
                processed_params.append(key)
            else:
                processed_params.append(f"{key}={urllib.parse.quote(str(value), safe='')}")
        processed_params = sorted(processed_params)
        return '&'.join(processed_params)

    @classmethod
    def data_processing3(cls, data):
        """
        此参数处理中，值为None或空值，需连接key值并后接等号
        如： {"transferTime": None, "withdrawAmount": "5.00"}
        转为： "transferTime=&withdrawAmount=5.00"
        """
        processed_params = []
        for key, value in data.items():
            if key == 'sign':
                continue
            if value is None or value == '':
                processed_params.append(f"{key}=")
            else:
                processed_params.append(f"{key}={value}")
        processed_params = sorted(processed_params)
        return '&'.join(processed_params)

    @classmethod
    def md5_sign(cls, data, api_key, key_name='key'):
        if key_name == 'AGDF':
            data = str(data['clientCode']) + "&" + str(data['chainName']) + "&" + str(data['coinUnit']) + "&"+ str(data['clientNo']) + "&" + str(data['requestTimestamp']) + api_key.strip()
        elif key_name == 'AGDF_notify':
            data = str(data['clientCode']) + "&" + str(data['clientNo']) + "&" + str(data['orderNo']) + "&"+ str(data['payAmount']) + "&" + str(data['status']) + "&" + str(data['txid']) + api_key.strip()
        elif key_name == 'AGDF_query':
            data = str(data['clientCode']) + "&" + str(data['clientNo']) + api_key.strip()
        elif key_name == 'KUAIYIN':
            data = f"{data['header_text']}{data['body_text']}{api_key.strip()}"
        elif key_name == 'catspay':
            data = cls.data_processing(data) + api_key.strip()
        else:
            data = cls.data_processing(data) + "&" + key_name + "=" + api_key.strip()
        md5 = hashlib.md5()
        md5.update(data.encode(encoding='UTF-8'))
        r = md5.hexdigest().upper()
        return r

    @classmethod
    def md5_sign2(cls, data, api_key):
        # 对数据进行排序
        sorted_data = sorted(data.items())
        sign_str = ''

        for pk, pv in sorted_data:
            if not pv or pk == 'sign':
                continue
            sign_str += f"{pk}={pv}&"

        sign_str += f"key={api_key}"

        # 计算 MD5 值并返回
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest()

    @staticmethod
    def get_md5_str(data_str):
        md5 = hashlib.md5()
        md5.update(data_str.encode(encoding='UTF-8'))
        r = md5.hexdigest()
        return r

    @classmethod
    def regex_process(cls, query_string):
        # 使用正则表达式替换空值的键值对，变成只有键名
        result = re.sub(r'([&?])([^=]+)=([^&]*)', lambda m: m.group(1) + m.group(2) if m.group(3) == '' else m.group(0), query_string)
        
        return result

    @classmethod
    def sha256_sign(cls, data, private_key_pem, flag=False, key_type='RSA', is_url=True):
        """
        sha256签名生成
        flag: 为True时，替换空值的键值对，变成只有键名
        key_type: 密钥格式。默认RSA，可选PKCS#8，参考对接文档中指定的密钥格式
        is_url: 是否对参数进行url编码处理，例如空格会编码成%20
        """
        if key_type == 'RSA':
            private_key_pem = """-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----""".format(private_key_pem)
        elif key_type == 'PKCS#8':
            private_key_pem = """-----BEGIN PRIVATE KEY-----\n{}\n-----END PRIVATE KEY-----""".format(private_key_pem)
        else:
            private_key_pem = """-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----""".format(private_key_pem)

        # 排序并转换成 URL 参数形式
        if is_url:
            sorted_params = sorted(data.items())
            sign_data = urllib.parse.urlencode(sorted_params, encoding='utf-8', doseq=True)
        else:
            sign_data = cls.data_processing(data)
        if flag:
            # 使用正则表达式处理
            sign_data = cls.regex_process(sign_data)
        # 加载私钥
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        # 进行 SHA256withRSA 签名
        signature = private_key.sign(
            sign_data.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        encoded_signature = base64.b64encode(signature).decode()
        return encoded_signature

    @classmethod
    def verify_rsasha1_sign(cls, public_key_pem, params, signature):
        """RSA SHA1签名验签"""
        excluded_fields = ['sign']
        filtered_params = {k: v for k, v in params.items() if k not in excluded_fields}
        # 2. 按照字典序排序参数
        sorted_params = sorted(filtered_params.items())
        # 对每个值进行 URL 编码并拼接
        encoded_params = "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_params if k not in ['sign'])  # 排除不参与签名的字段
        # 4. 格式化并载入公钥
        public_key_pem = """-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----""".format(public_key_pem)
        try:
            # 载入公钥
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode(),
                backend=default_backend()
            )
            print("公钥加载成功")
        except Exception as e:
            print(f"公钥加载失败: {e}")
            return False
        # 5. 解码签名
        try:
            signature_bytes = base64.b64decode(signature)
            print(f"解码后的签名字节: {signature_bytes}")
        except Exception as e:
            print(f"签名解码失败: {e}")
            return False
        # 6. 执行验签
        try:
            public_key.verify(
                signature_bytes,
                encoded_params.encode(),  # 确保 data 为字节类型
                padding.PKCS1v15(),
                hashes.SHA1()
            )
            print("验签成功")
            return True  # 验签成功
        except Exception as e:
            print(f"验签失败: {e}")
            return False  # 验签失败
        
    @classmethod
    def verify_sha256_sign(cls, public_key_pem, params, signature):
        """sha256签名验签"""
        data = cls.data_processing2(params)

        public_key_pem = """-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----""".format(public_key_pem)

        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )
        signature_bytes = base64.b64decode(signature)

        try:
            public_key.verify(
                signature_bytes,
                data.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True  # 验签成功
        except Exception as e:
            print(f"验签失败: {e}")
            return False  # 验签失败

    @classmethod
    def rsa_sha1_sign(cls, data, private_key_pem):
            """使用 RSA 私钥对数据进行 SHA1 签名"""
            private_key_pem = """-----BEGIN PRIVATE KEY-----\n{}\n-----END PRIVATE KEY-----""".format(private_key_pem)
            # 1. 过滤掉值为空的参数（保留 0、False）
            filtered_data = {k: v for k, v in data.items() if v is not None and v != ""}
            # 2. 按参数名 ASCII 码顺序排序
            sorted_params = sorted(filtered_data.items())
            # 3. URL 编码值，并拼接成签名字符串（确保空格转换为 +）
            sign_data = urllib.parse.urlencode(sorted_params, encoding='utf-8', doseq=False)
            try:
                # 4. 解析 PKCS#8 私钥
                private_key = serialization.load_pem_private_key(
                    private_key_pem.encode(),  # 确保私钥是字节格式
                    password=None,
                    backend=default_backend()
                )
                # 5. 进行 SHA1 with RSA 签名
                signature = private_key.sign(
                    sign_data.encode(),  # 需要签名的数据（字节格式）
                    padding.PKCS1v15(),  # 填充方式
                    hashes.SHA1()  # 哈希算法
                )
                # 6. 对签名结果进行 Base64 编码
                encoded_signature = base64.b64encode(signature).decode()
                return encoded_signature
            except Exception as e:
                raise ValueError(f"签名失败: {str(e)}")
    @classmethod
    def sha1_sign(cls, data, private_key_pem, flag=False):
        """sha1签名生成"""
        private_key_pem = """-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----""".format(private_key_pem)
        # 排序并转换成 URL 参数形式
        sorted_params = sorted(data.items())
        sign_data = urllib.parse.urlencode(sorted_params, encoding='utf-8', doseq=True)
        # 加载私钥
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
        # 进行 SHA1withRSA 签名
        signature = private_key.sign(
            sign_data.encode(),
            padding.PKCS1v15(),
            hashes.SHA1()
        )
        encoded_signature = base64.b64encode(signature).decode()
        return encoded_signature

    @classmethod
    def verify_sha1_sign(cls, public_key_pem, params, signature):
        """sha1签名验签"""
        data = cls.data_processing2(params)

        public_key_pem = """-----BEGIN PUBLIC KEY-----\n{}\n-----END PUBLIC KEY-----""".format(public_key_pem)

        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )
        signature_bytes = base64.b64decode(signature)

        try:
            public_key.verify(
                signature_bytes,
                data.encode(),
                padding.PKCS1v15(),
                hashes.SHA1()
            )
            return True  # 验签成功
        except Exception as e:
            print(f"验签失败: {e}")
            return False  # 验签失败


    @classmethod
    def md5_verify(cls, data, signature, api_key, key_name='key'):
        if cls.md5_sign(data, api_key, key_name=key_name) == signature:
            return True
        else:
            return False

    @classmethod
    def hash_hmac(cls, key, code, sha1):
        hmac_code = hmac.new(key.encode(), code.encode(), sha1).digest()
        return base64.b64encode(hmac_code).decode()

    @classmethod
    def data_processing_withnull(cls, data):
        """
        :param data: 需要签名的数据，字典类型
        :return: 处理后的字符串，格式为：参数名称=参数值，并用&连接
        """
        if "sign" in data:
            del data["sign"]
        if "sign_type" in data:
            del data["sign_type"]
        dataList = []
        for key in sorted(data):
            dataList.append("%s=%s" % (key, data[key]))
        return "&".join(dataList).strip()

    @classmethod
    def sign_withnull(cls, data, api_key):
        data = cls.data_processing_withnull(data) + "&key=" + api_key.strip()
        md5 = hashlib.md5()
        md5.update(data.encode(encoding='UTF-8'))
        r = md5.hexdigest().upper()
        return r

    @classmethod
    def md5_verifywithnull(cls, data, signature, api_key):
        """
        md5验签
        :param data: 接收到的数据
        :param signature: 接收到的sign
        :return: 验签结果,布尔值
        """

        if cls.sign_withnull(data, api_key) == signature:
            return True
        else:
            return False

    @classmethod
    def hmac_sha256_sign(cls, data: dict, secret_key: str) -> str:
        """
        生成 HMAC-SHA256 签名

        参数说明：
        params - 包含所有请求参数的字典(需包含除sign外的所有有效参数)
        secret_key - 商户平台分配的密钥

        返回：
        Base64编码的签名字符串
        """
        # 构造签名字符串
        sign_str = cls.data_processing(data)

        # 计算HMAC-SHA256
        digest = hmac.new(
            secret_key.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).digest()

        # Base64编码
        return base64.b64encode(digest).decode('utf-8').strip()

    @classmethod
    def hmac_sha256_sign3(cls, data: dict, secret_key: str) -> str:
        """
        生成 HMAC-SHA256 签名

        参数说明：
        params - 包含所有请求参数的字典(需包含除sign外的所有有效参数)
        secret_key - 商户平台分配的密钥

        返回：
        Base64编码的签名字符串
        """
        # 构造签名字符串
        sign_str = cls.data_processing3(data)

        # 计算HMAC-SHA256
        digest = hmac.new(
            secret_key.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).digest()

        # Base64编码
        return base64.b64encode(digest).decode('utf-8').strip()

    @classmethod
    def verify_hmac_sha256(cls, secret_key: str, data: dict, received_sign: str) -> bool:
        """
        HMAC-SHA256签名验证
        """
        sign_str = cls.data_processing(data)
        expected_sign = hmac.new(
            secret_key.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).digest()

        try:
            return hmac.compare_digest(
                expected_sign,
                base64.b64decode(received_sign)
            )
        except (TypeError, ValueError):
            return False

    @classmethod
    def generate_signature_skpay(cls, method, url_path, access_key, access_secret):
        method = method.upper()  # 确保是大写
        timestamp = str(int(time.time()))
        nonce = str(random.randint(100000, 999999))
        # 拼接字符串
        raw_string = f"{method}&{url_path}&{access_key}&{timestamp}&{nonce}"
        # HMAC-SHA256 + Base64
        # 生成 HMAC-SHA256，然后 Base64 编码
        hmac_obj = hmac.new(access_secret.encode(), raw_string.encode(), hashlib.sha256)
        sign = base64.b64encode(hmac_obj.digest()).decode()
        # 返回签名相关参数
        return {
            "sign": sign,
            "timestamp": timestamp,
            "nonce": nonce
        }
        
    @classmethod
    def verify_signature_skpay(cls, raw_string, access_secret, signature):
        # 生成 HMAC-SHA256，然后 Base64 编码
        # HMAC-SHA256 加密
        hmac_obj = hmac.new(access_secret.encode(), raw_string.encode(), hashlib.sha256)
        sign = base64.b64encode(hmac_obj.digest()).decode()
        # print(sign)
        print('取得签名=====', sign)
        if sign == signature:
            return True
        else:
            return False

    @classmethod
    def aes_256_cbc_encrypt(cls, key, iv, data):
        cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        encrypted = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')

    @classmethod
    def aes_256_cbc_decrypt(cls, key, iv, data):
        cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        decrypted = cipher.decrypt(base64.b64decode(data))
        return unpad(decrypted, AES.block_size).decode('utf-8')
