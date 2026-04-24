class Beneficiary:
    def __init__(self):
        self.bene_ifsc: str = ""
        self.bene_acc_no: str = ""
        self.bene_name: str = ""
        self.nick_name: str = ""
        self.mobile_no: str = ""
        self.beneficiary_status: str = ""
        self.bene_account_type: str = ""
        self.orders_df_code: str = ""
        self.transfer_amount: float = 0.0
        self.payment_mode: str = "NEFT"
        self.utr: str = ""

    def to_dict(self) -> dict:
        """将对象转换为字典"""
        return {
            'bene_ifsc': self.bene_ifsc,
            'bene_acc_no': self.bene_acc_no,
            'bene_name': self.bene_name,
            'nick_name': self.nick_name,
            'mobile_no': self.mobile_no,
            'beneficiary_status': self.beneficiary_status,
            'bene_account_type': self.bene_account_type,
            'orders_df_code': self.orders_df_code,
            'transfer_amount': self.transfer_amount,
            'payment_mode': self.payment_mode,
            'utr': self.utr
        }

    def __str__(self) -> str:
        """将对象转换为JSON字符串"""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'Beneficiary':
        """从JSON字符串创建Beneficiary对象

        Args:
            json_str: JSON字符串

        Returns:
            Beneficiary: 新的Beneficiary对象
        """
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'Beneficiary':
        """从字典创建Beneficiary对象

        Args:
            data: 包含Beneficiary数据的字典

        Returns:
            Beneficiary: 新的Beneficiary对象
        """
        obj = cls()
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj
