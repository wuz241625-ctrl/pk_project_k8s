from tornado.web import url

from application.phonepe import phmonitor
from application.phonepe import phmonitorHttp
from application.app.websocket import app
from application.pay import pay, order, status, thirdCallback
from application.pay.easypay_handler import EasypayInitiate
from application.websocket import monitor
from application.websocket import monitor_http
from application.third import third_df
from application.bot import bot

urls = [
    # api相关
    url("/pay", pay.Pay),  # 代收下单
    url('/pay/ds/utr', pay.ds_utr),  # 代收订单UTR补单
    url("/pay/df", pay.Pay_df),  # 代付下单
    url('/status/ds', status.Status_ds),  # 代收订单状态查询
    url('/status/df', status.Status_df),  # 代付订单状态查询
    url('/balance', status.Balance),  # 代付订单状态查询
    url('/order/Success', order.Success, name='orderSuccess'),  # 账单成功回调
    url('/order/successBot', order.SuccessBot, name='orderSuccessBot'),  # 机器人账单成功回调
    url(r'/api/ord/card_num/(?P<token>\S+)', order.card_num, name='card_num_submit'),  # 提交卡密
    url('/api/ord/download_count_submit', order.download_count_submit, name='download_count_submit'),  # 统计下载次数

    url('/api/ord/order_statu/(?P<token>\S+)', order.Status, name='orderStatus'),  # 提交卡密
    url('/ord/card_num/(?P<token>\S+)', order.card_num, name='card_num_submit1'),  # 提交卡密
    url('/ord/order_statu/(?P<token>\S+)', order.Status, name='orderStatus1'),  # 提交卡密
    url('/order/(?P<token>\S+)', order.Order, name='orderQrcode'),  # 支付提交
    url("/files/upload", app.issue.upload, name='upload'),
    # APP websocket
    url("/partner/ws", app.Websocket, name='app_Websocket'),
    # 监控 websocket 长连接协议
    url("/monitor/ws", monitor.Websocket, name='monitor_Websocket'),
    url(r"/monitor/http", monitor_http.Websocket, name="monitor_http"),
    # phonepe 短链接协议开发
    url("/phonepe/ws", phmonitor.Websocket, name='phonepe_Websocket'),
    # phonepe 短链接协议开发
    url("/phonepe/api/login", phmonitorHttp.LoginHandler),
    url("/phonepe/api/online", phmonitorHttp.OnlineHandler),
    url("/phonepe/api/offline", phmonitorHttp.OfflineHandler),
    url("/phonepe/api/upi", phmonitorHttp.UpiHandler),
    url("/phonepe/api/new", phmonitorHttp.NewHandler),
    # phonepe
    url("/phonepe/ws", phmonitor.Websocket, name='phonepe_Websocket'),
    # 代付外接
    url('/df_notice/AGDF', third_df.AGDF_Pay, name='notice_AGDF_Pay'),  # AG代付 notice
    url('/df_notice/cubpay', third_df.CUB_Pay, name='notice_CUB_Pay'),  # cubpay notice
    url('/df_notice/wallet', third_df.WALLET_Pay, name='notice_WALLET_Pay'),  # wallet notice
    url('/df_notice/haoda', third_df.Haoda_Pay, name='notice_Haoda_Pay'),  # haoda notice
    url('/df_notice/happypay', third_df.HAPPY_Pay, name='notice_Happy_Pay'),  # happypay notice
    url('/df_notice/kingpay', third_df.King_Pay, name='notice_King_Pay'),  # kingpay notice
    url('/df_notice/kingpay2', third_df.King_Pay2, name='notice_King_Pay2'),  # kingpay2 notice
    url('/df_notice/razopay', third_df.Razo_Pay, name='notice_Razo_Pay'),  # razopay notice
    url('/df_notice/ydpay', third_df.YD_Pay, name='notice_YD_Pay'),  # ydpay notice
    url('/df_notice/sdpay', third_df.SD_Pay, name='notice_SD_Pay'),  # sdpay notice
    url('/df_notice/queen', third_df.Queen_Pay, name='notice_Queen_Pay'),  # queen notice
    url('/df_notice/inpay', third_df.IN_Pay, name='notice_IN_Pay'),  # inpay notice
    url('/df_notice/redpay', third_df.RED_Pay, name='notice_RED_Pay'),  # redpay notice
    url('/df_notice/lucky', third_df.LUCKY_Pay, name='notice_LUCKY_Pay'),  # Lucky notice
    url('/df_notice/apay', third_df.APay, name='notice_APAY_Pay'),  # APay notice
    url('/df_notice/globe', third_df.Globe, name='notice_GLOBE_Pay'),  # Globe notice
    url('/df_notice/rupix', third_df.Rupix, name='notice_RUPIX_Pay'),  # Rupix notice
    url('/df_notice/pay58pay', third_df.Pay58pay, name='notice_58_PAY_Pay'),  # Pay58pay notice
    url('/df_notice/kuaiyin', third_df.Kuaiyinpay, name='notice_KUAIYIN_Pay'),  # Kuaiyinpay notice
    url('/df_notice/wepay', third_df.Wepay, name='notice_WE_Pay'),  # wepay notice
    url('/df_notice/lemonpay', third_df.Lemonpay, name='notice_LEMON_Pay'),  # lemonpay notice
    url('/df_notice/pay777pay', third_df.Pay777Pay, name='notice_777_Pay'),  # 777pay notice
    url('/df_notice/swiftpay', third_df.SwiftPay, name='notice_swift_Pay'),  # SwiftPay notice
    url('/df_notice/lemonpay2', third_df.LemonPay2, name='notice_lemonpay2_Pay'),  # LemonPay2 notice
    url('/df_notice/quickpay', third_df.Quickpay, name='notice_quick_Pay'),  # Quickpay notice
    url('/df_notice/snakepay', third_df.SnakePay, name='notice_snakepay_Pay'),  # SnakePay notice
    url('/df_notice/hkpay', third_df.Hkpay, name='notice_hkpay_Pay'),  # hkpay notice
    url('/df_notice/skpay', third_df.SkPay, name='notice_skpay_Pay'),  # skpay notice
    url('/df_notice/catspay', third_df.CatsPay, name='notice_catspay_Pay'),  # catspay notice
    url('/df_notice/lemonpay3', third_df.LemonPay3, name='notice_lemonpay3_Pay'),  # lemonpay3 notice
    url('/df_notice/188pay', third_df.Pay188Pay, name='notice_188pay_Pay'),  # 188pay notice
    url('/df_notice/tatapay', third_df.TataPay, name='notice_tatapay_Pay'),  # TataPay notice
    url('/df_notice/ospay', third_df.OsPay, name='notice_ospay_Pay'),  # ospay notice
    url('/df_notice/vibrapay', third_df.VibraPay, name='notice_vibrapay_Pay'),  # vibrapay notice
    url('/df_notice/qqpay', third_df.qqpay, name='notice_qqpay'),  # qqpay notice
    url('/df_notice/marspay', third_df.marspay, name='notice_marspay'),  # marspay notice
    url('/df_notice/gamepayer', third_df.gamepayer, name='notice_gamepayer'),  # gamepayer notice

    url("/apay_notify", thirdCallback.ApayNotify, name='apay_notify'),  # apay_notify代收通知地址
    url("/lucky_notify", thirdCallback.lucky_notify, name='lucky_notify'),  # lucky_notify代收通知地址
    url("/kingpay_notify", thirdCallback.kingpay_notify, name='kingpay_notify'),  # kingpay_notify代收通知地址
    url("/kingpay_notify2", thirdCallback.KingpayNotify2, name='kingpay_notify2'),  # kingpay_notify2代收通知地址
    url("/wepay_notify", thirdCallback.wepay_notify, name='wepay_notify'),  # wepay_notify代收通知地址
    url("/777_notify", thirdCallback.Pay777PayNotify, name='pay777pay_notify'),  # pay777pay_notify代收通知地址
    url("/swiftpay_notify", thirdCallback.SwiftPayNotify, name='swiftpay_notify'),  # swiftpay_notify代收通知地址
    url("/quickpay_notify", thirdCallback.quickpay_notify, name='quickpay_notify'),  # quickpay_notify代收通知地址
    url("/snakepay_notify", thirdCallback.SnakePayNotify, name='snakepay_notify'),  # snakepay_notify代收通知地址
    url("/hkpay_notify", thirdCallback.hkpay_notify, name='hkpay_notify'),  # hkpay_notify代收通知地址
    url("/skpay_notify", thirdCallback.skpay_notify, name='skpay_notify'),  # skpay_notify代收通知地址
    url("/ospay_notify", thirdCallback.OsPayNotify, name='ospay_notify'),  # ospay_notify代收通知地址
    url("/tatapay_notify", thirdCallback.tatapay_notify, name='tatapay_notify'),  # tatapay_notify代收通知地址
    url("/vibrapay_notify", thirdCallback.vibrapay_notify, name='vibrapay_notify'),  # tatapay_notify代收通知地址
    url("/qqpay_notify", thirdCallback.qqpay_notify, name='qqpay_notify'),  # qqpay_notify代收通知地址
    url("/gamepayer_notify", thirdCallback.gamepayer_notify, name='gamepayer_notify'),  # gamepayer_notify代收通知地址
    url("/easypay/initiate", EasypayInitiate, name='easypay_initiate'),  # easypay SOAP 代收：用户输入手机号后发起付款

    url("/bot/upi/payment_exist", bot.ExistPaymentByUpi, name='payment_exist'),  # 根据upi 查询payment是否存在
    url("/bot/order_id/receipt", bot.getReceiptByOrderId, name='getreceiptbyid'),   # 根据订单id 查询代付订单回执
    url(r"/bot/command/(?P<cmd>\S+)", bot.commandListener, name='commandListener'),   # 根据订单id 查询代付订单回执
]
