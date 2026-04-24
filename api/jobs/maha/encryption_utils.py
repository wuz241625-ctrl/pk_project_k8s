import base64
import hashlib
import random
import string
import sys

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2

# 常量定义
UTF_8 = 'utf-8'
AES_GCM_NO_PADDING = 'AES/GCM/NoPadding'
PBKDF2_WITH_HMAC_SHA1 = 'PBKDF2WithHmacSHA1'
GCM_TAG_LENGTH = 128  # bits
KEY_LENGTH = 128  # bits
ITERATION_COUNT = 100

class EncryptionUtils:

    @staticmethod
    def encrypt_password(password: str) -> str:
        """
        使用 SHA-512 计算密码哈希值。

        :param password: 需要哈希的密码
        :return: 十六进制格式的哈希字符串
        """
        try:
            # 创建 SHA-512 哈希对象
            hash_bytes = hashlib.sha512(password.encode(UTF_8)).digest()
            # 转换为十六进制字符串
            return ''.join(f'{b:02x}' for b in hash_bytes)
        except Exception as e:
            print(f"Password encryption failed: {e}", file=sys.stderr)
            return None

    @staticmethod
    def decrypt(encrypted_str: str, secret_key: str) -> str:
        """
        使用 AES-GCM 算法解密数据。

        :param encrypted_str: Base64编码的加密数据
        :param secret_key: 密钥
        :return: 解密后的字符串
        """
        try:
            # 将密钥转换为字节
            key_bytes = secret_key.encode(UTF_8)

            # 固定 IV（初始化向量），取前 16 字节
            iv_string = "3e1d4d99b9befcf45d9062390ab34671f904ba61"[:16]
            iv_bytes = iv_string.encode(UTF_8)

            # 创建 AES-GCM 解密器
            cipher = AES.new(key_bytes, AES.MODE_GCM, nonce=iv_bytes)

            # 解码Base64数据
            decoded_data = base64.b64decode(encrypted_str)

            # 分离加密数据和认证标签
            ciphertext = decoded_data[:-16]
            tag = decoded_data[-16:]

            # 设置认证标签并解密
            cipher.update(b'')
            decrypted_bytes = cipher.decrypt_and_verify(ciphertext, tag)

            return decrypted_bytes.decode(UTF_8)
        except Exception as e:
            print(f"Decryption failed: {e}", file=sys.stderr)
            return None

    @staticmethod
    def encrypt(data: str, secret_key: str) -> str:
        """
        使用 AES-GCM 算法加密数据。

        :param data: 需要加密的原始数据
        :param secret_key: 密钥
        :return: 加密后的数据（Base64 编码）
        """
        try:
            # 将密钥转换为字节
            key_bytes = secret_key.encode(UTF_8)

            # 固定 IV（初始化向量），取前 16 字节
            iv_string = "3e1d4d99b9befcf45d9062390ab34671f904ba61"[:16]
            iv_bytes = iv_string.encode(UTF_8)

            # 创建 AES-GCM 加密器
            cipher = AES.new(key_bytes, AES.MODE_GCM, nonce=iv_bytes)

            # 加密数据
            data_bytes = data.encode(UTF_8)
            encrypted_bytes, tag = cipher.encrypt_and_digest(data_bytes)

            # 将加密后的数据和认证标签组合
            combined = encrypted_bytes + tag

            # 将加密后的数据编码为 Base64
            encoded = base64.b64encode(combined).decode(UTF_8)

            # 去除 Base64 中的换行符
            return encoded.replace("\r", "").replace("\n", "")
        except Exception as e:
            print(f"Encryption failed: {e}", file=sys.stderr)
            return ""

    @staticmethod
    def gen_key(key_value: str, salt: str) -> str:
        """
        使用 PBKDF2 算法生成密钥。

        :param key_value: 密钥值
        :param salt: 盐值
        :return: 生成的密钥（Base64 编码的前 16 位）
        """
        if not key_value or not salt:
            return None
        try:
            # 将密钥值和盐转换为字节
            key_bytes = key_value.encode(UTF_8)
            salt_bytes = salt.encode(UTF_8)
            # 使用 PBKDF2 生成密钥
            derived_key = PBKDF2(key_bytes, salt_bytes, dkLen=KEY_LENGTH,
                                 count=ITERATION_COUNT)
            # 将密钥编码为 Base64
            encoded_key = base64.b64encode(derived_key).decode(UTF_8)
            # 取前 16 位
            return encoded_key[:16]
        except Exception as e:
            print(f"Key generation failed: {e}")
            return None

    @staticmethod
    def get_random_string(length: int) -> str:
        """
        生成指定长度的随机字符串。

        :param length: 要生成的字符串长度
        :return: 随机字符串
        """
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

# 示例用法
if __name__ == "__main__":
    # 测试加密
    data = "123456"
    secret_key = "6YmS/VkOKtiFasoI"

    encryptionUtils = EncryptionUtils()

    # 测试密码加密
    print(f"Password Hash: {encryptionUtils.encrypt_password('test_password')}")

    # 测试AES加密和解密
    encrypted_data = encryptionUtils.encrypt(data, secret_key)
    print(f"Encrypted: {encrypted_data}")
    decrypted_data = encryptionUtils.decrypt(encrypted_data, secret_key)
    print(f"Decrypted: {decrypted_data}")

    # 测试密钥生成
    key = encryptionUtils.gen_key("test_key", "test_salt")
    print(f"Generated Key: {key}")

    # 测试随机字符串生成
    random_str = encryptionUtils.get_random_string(6)
    print(f"Random String: {random_str}")
