from enum import Enum, auto

from maha_result_status_attributes import MahaResultStatusAttributes

"""
支付流程的状态
"""
class PayProcessStatus(Enum):
    TO_PAY = "to_pay" # 成功添加受益人，去支付
    PAID_SUCCESS = "paid_success" # 付款成功
    FAILED_TO_PAID = "failed_to_paid" # 付款失败
    INVALID_ADD_BENEFICIARY_INFO = "invalid_add_beneficiary_info" # 添加的受益人信息无效
    WAITING_FOR_AUDIT_ADD_BENEFICIARY = "waiting_for_audit_add_beneficiary" # 添加受益人等待审核
    FAILED_ADD_BENEFICIARY = "failed_add_beneficiary" # 添加受益人失败
    REJECTED_ADD_BENEFICIARY = "rejected_add_beneficiary" # 添加受益人审核驳回

    # 从字符串转换为枚举值
    def string_to_enum(enum_str: str):
        try:
            # 方法 1：使用枚举类的构造函数
            enum = PayProcessStatus(enum_str)
            return enum
        except ValueError:
            try:
                # 方法 2：直接访问枚举成员
                enum = PayProcessStatus[enum_str.upper()]
                return enum
            except KeyError:
                return None

# 定义枚举类
class MahaResultStatusCode(Enum):
    # 定义枚举成员，每个成员的值是 MahaResultStatusAttributes 的实例
    TRUE = MahaResultStatusAttributes(
        code=200,
        description="正常",
        en_cue_words="ok",
        zh_cue_words="正常",
    )
    FALSE = MahaResultStatusAttributes(
        description="错误",
        en_cue_words="false",
        zh_cue_words="错误",
    )
    NO_PROXY = MahaResultStatusAttributes(
        description="没有代理",
        en_cue_words="no proxy",
        zh_cue_words="未设置代理",
    )
    RETRY = MahaResultStatusAttributes(
        description="需要重试",
        en_cue_words="Please try again later.",
        zh_cue_words="请稍后重试",
    )
    LOGOUT = MahaResultStatusAttributes(
        description="协议下线",
        en_cue_words="protocol offline",
        zh_cue_words="协议下线",
    )
    DEVICE_LOCKED = MahaResultStatusAttributes(
        description="设备被锁",
        en_cue_words="",
        zh_cue_words="",
    )
    RESET_TPIN = MahaResultStatusAttributes(
        description="重置TPIN",
        en_cue_words="",
        zh_cue_words="",
    )
    TPIN_ERROR = MahaResultStatusAttributes(
        description="tpin错误",
        en_cue_words="",
        zh_cue_words="",
    )
    SESSION_EXPIRED = MahaResultStatusAttributes(
        description="Session过期",
        en_cue_words="",
        zh_cue_words="",
    )
    ADDED_BENEFICIARY_FAILED = MahaResultStatusAttributes(
        description="添加的受益人失败",
        en_cue_words="",
        zh_cue_words="",
    )
    BENEFICIARY_INFO_ERROR = MahaResultStatusAttributes(
        description="受益人信息错误，取消订单",
        en_cue_words="Query beneficiary info failed, please try again later",
        zh_cue_words="Query beneficiary info failed, please try again later",
    )
    ADDED_BENEFICIARY_AUDITING = MahaResultStatusAttributes(
        description="添加的受益人审核中",
        en_cue_words="",
        zh_cue_words="",
    )
    FAIL_TO_APPROVE_BENEFICIARY = MahaResultStatusAttributes(
        description="申请审核受益人失败，需要再次申请",
        en_cue_words="Fail to approve beneficiary.",
        zh_cue_words="申请审核受益人失败，需要再次申请",
    )
    ADDED_BENEFICIARY_REPEAT = MahaResultStatusAttributes(
        description="添加的受益人重复",
        en_cue_words="Beneficiary with given Nick Name already exists.",
        zh_cue_words="添加的受益人重复",
    )
    PAID_SUCCESS = MahaResultStatusAttributes(
        description="付款成功",
        en_cue_words="",
        zh_cue_words="",
    )
    BALANCE_INSUFFICIENT = MahaResultStatusAttributes(
        description="余额不足",
        en_cue_words="Insufficient available balance",
        zh_cue_words="余额不足",
    )
    RESPONSE_01_FAILED = MahaResultStatusAttributes(
        description="响应 01 FAILED",
        en_cue_words="",
        zh_cue_words="",
    )
    ACCOUNT_BLOCKED = MahaResultStatusAttributes(
        description="查询账户时遇到暂时无法处理的原因",
        en_cue_words="There was a problem reading the account. Please try again later.",
        zh_cue_words="查询账户时遇到暂时无法处理的原因",
    )
    CANNOT_TRANSFER_TO_YOURSELF = MahaResultStatusAttributes(
        description="无法给自己转账",
        en_cue_words="You can't transfer money to yourself",
        zh_cue_words="不能转账给自己",
    )
    FUND_SOME_CONNECTIVITY_ISSUES = MahaResultStatusAttributes(
        description="转账请求太多，稍后再试",
        en_cue_words="There are some connectivity issues, please try after sometime.",
        zh_cue_words="转账请求太多，稍后再试",
    )
    TRANSFER_BLOCKED = MahaResultStatusAttributes(
        description="转账遇到暂时无法处理的原因",
        en_cue_words="An error occurred while transferring the money. Please try again later.",
        zh_cue_words="转账遇到暂时无法处理的原因",
    )
    KEEP_WAITING = MahaResultStatusAttributes(
        description="继续等待",
        en_cue_words="Keep waiting",
        zh_cue_words="继续等待",
    )

    # 直接访问属性
    @property
    def description(self):
        return self.value.description

    @property
    def en_cue_words(self):
        return self.value.en_cue_words

    @property
    def zh_cue_words(self):
        return self.value.zh_cue_words


if __name__ == '__main__':
    enums = MahaResultStatusCode.TRUE
    print(enums)
    print(enums.description)
    print(enums.en_cue_words)
    print(enums.zh_cue_words)
    
    e1 = PayProcessStatus.TO_PAY
    print(e1)
    print(e1.name)
    print(e1.value)
