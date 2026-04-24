class AccountBalance:
    def __init__(self, available_balance: str, current_balance: str, amount_on_hold: str):
        """
        初始化 BalanceInfo 对象。

        :param available_balance: 可用余额（字符串）
        :param current_balance: 当前余额（字符串）
        :param amount_on_hold: 滞留余额（字符串）
        """
        # 将字符串转换为 float 类型
        self.AvailableBalance: float = float(available_balance)
        self.CurrentBalance: float = float(current_balance)
        self.AmountOnHold: float = float(amount_on_hold)

    def to_dict(self) -> dict:
        """
        将对象转换为字典。

        :return: 包含对象属性的字典
        """
        return {
            "AvailableBalance": self.AvailableBalance,
            "CurrentBalance": self.CurrentBalance,
            "AmountOnHold": self.AmountOnHold
        }

    @classmethod
    def from_dict(cls, data: dict):
        """
        从字典创建 BalanceInfo 对象。

        :param data: 包含对象属性的字典
        :return: BalanceInfo 对象
        """
        return cls(
            available_balance=str(data.get("AvailableBalance")),
            current_balance=str(data.get("CurrentBalance")),
            amount_on_hold=str(data.get("AmountOnHold"))
        )

    def __str__(self) -> str:
        """
        返回对象的字符串表示。

        :return: 对象的字符串表示
        """
        return f"AvailableBalance: {self.AvailableBalance}, CurrentBalance: {self.CurrentBalance}, AmountOnHold: {self.AmountOnHold}"

    def to_json(self) -> str:
        """
        将对象转换为 JSON 字符串。

        :return: JSON 格式的字符串
        """
        import json
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str):
        """
        从 JSON 字符串创建 BalanceInfo 对象。

        :param json_str: JSON 格式的字符串
        :return: BalanceInfo 对象
        """
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)


# 示例用法
if __name__ == "__main__":
    # 创建对象（传入字符串）
    balance_info = AccountBalance(
        available_balance="3407.70",
        current_balance="10057.70",
        amount_on_hold="6650.00"
    )

    # 输出对象字符串表示
    print(balance_info)  # 输出: AvailableBalance: 3407.7, CurrentBalance: 10057.7, AmountOnHold: 6650.0

    # 转换为字典
    balance_dict = balance_info.to_dict()
    print(balance_dict)  # 输出: {'AvailableBalance': 3407.7, 'CurrentBalance': 10057.7, 'AmountOnHold': 6650.0}

    # 从字典创建对象
    new_balance_info = AccountBalance.from_dict(balance_dict)
    print(new_balance_info)  # 输出: AvailableBalance: 3407.7, CurrentBalance: 10057.7, AmountOnHold: 6650.0

    # 转换为 JSON 字符串
    json_str = balance_info.to_json()
    print(json_str)  # 输出: {"AvailableBalance": 3407.7, "CurrentBalance": 10057.7, "AmountOnHold": 6650.0}

    # 从 JSON 字符串创建对象
    new_balance_info_from_json = AccountBalance.from_json(json_str)
    print(new_balance_info_from_json)  # 输出: AvailableBalance: 3407.7, CurrentBalance: 10057.7, AmountOnHold: 6650.0