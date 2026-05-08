"""Shared utility functions for payout modules."""


def is_pakistan_mobile_number(account_number: str) -> bool:
    """判断是否为巴基斯坦手机号（EasyPaisa账号格式）

    巴基斯坦手机号格式：
    - 以 03 开头，总共11位数字（本地格式 03XXXXXXXXX）
    - 以 92 开头，总共13位数字（国际格式 923XXXXXXXXX）
    """
    if not account_number:
        return False

    clean_number = ''.join(filter(str.isdigit, str(account_number)))

    if len(clean_number) == 11 and clean_number.startswith('03'):
        return True
    if len(clean_number) == 13 and clean_number.startswith('923'):
        return True
    return False
