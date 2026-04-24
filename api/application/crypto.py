from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64

"""
密钥 (KEY) :
初始化向量 (IV):
加密模式 (AES-256-CBC) 和
填充模式 (PKCS7):
"""

# AES-256-CBC
KEY = b'bo3ubug9j645w3gg4op499n62e6phdtc'
IV = b'z3i6mcglw4frk3cl'

def encrypt(plain_text):
    if not plain_text:
        return None
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    cipher_text = cipher.encrypt(pad(plain_text.encode(), AES.block_size))
    return base64.b64encode(cipher_text).decode()

def decrypt(cipher_text):
    if not cipher_text:
        return None
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    decrypted_text = unpad(cipher.decrypt(base64.b64decode(cipher_text)), AES.block_size)
    return decrypted_text.decode()

if __name__ == '__main__':
    # Example usage
    encrypted = encrypt("4321")
    print("Encrypted:", encrypted)
    encrypted = "XrAzQwwKduEA/SKUi8yLhw=="
    decrypted = decrypt(encrypted)
    print("Decrypted:", decrypted)
