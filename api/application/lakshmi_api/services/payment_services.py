from application.lakshmi_api.services.payments.freecharge_service import FreechargeService
from application.lakshmi_api.services.payments.indus_pay_service import IndusPayService
from application.lakshmi_api.services.payments.maha_service import MahaService
from application.lakshmi_api.services.payments.phonepe_service import PhonepeService
from application.lakshmi_api.services.payments.mobikwik_service import MobikwikService
from application.lakshmi_api.services.payments.airtel_service import AirtelService
from application.lakshmi_api.services.payments.amazon_pay_service import AmazonService
from application.lakshmi_api.services.payments.ulcash_service import UlCashPayService
from application.lakshmi_api.services.payments.jio_service import JioService
from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService
from application.lakshmi_api.services.payments.jazzcash_pay_service import JazzCashPayService

BANK_SERVICES = {
    "FREECHARGE": FreechargeService,
    "PHONEPE": PhonepeService,
    "MOBIKWIK": MobikwikService,
    "AIRTEL": AirtelService,
    "AMAZON": AmazonService,
    "INDUS": IndusPayService,
    "ULCASH": UlCashPayService,
    "JIO": JioService,
    "MAHA": MahaService,
    "EASYPAISA": EasyPaisaPayService,
    "JAZZCASH": JazzCashPayService,
}
