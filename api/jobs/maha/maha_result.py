from typing import Optional

from base_class import BaseClass
from account_balance import AccountBalance
from beneficiary import Beneficiary
from maha_result_status import MahaResultStatusCode
from user_info import UserInfo


class MahaResult(BaseClass):

    def __init__(
        self,
        is_success: bool = False,
        status_code: MahaResultStatusCode = MahaResultStatusCode.FALSE,
        data: dict = None,
        user_info: Optional[UserInfo] = None,
        beneficiary: Optional[Beneficiary] = None,
        error_message: str = "",
        orders_df: dict = None,
        account_balance: AccountBalance = None,
    ):
        self.is_success = is_success
        self.status_code = status_code
        self.data = data
        self.user_info = user_info
        self.beneficiary = beneficiary
        self.error_message = error_message
        self.orders_df = orders_df
        self.account_balance = account_balance

if __name__ == '__main__':
    ben = Beneficiary()
    ben.bene_name = "abc"
    mahaResult = MahaResult(status_code=MahaResultStatusCode.LOGOUT, error_message="", beneficiary=ben)
    print(mahaResult.to_json_str())
