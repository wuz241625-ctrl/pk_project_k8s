from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService
from application.lakshmi_api.services.payments.jazzcash_pay_service import JazzCashPayService

BANK_SERVICES = {
    "EASYPAISA": EasyPaisaPayService,
    "JAZZCASH": JazzCashPayService,
}
