import os

from tornado.web import url

from application.lakshmi_api.controllers import (
    user_controller, deposit_orders_controller, content_controller, users_controller, withdraw_orders_controller,
    upi_controller, members_controller, ws_demo_controller, websockets_controller, usdt_orders_controller,
    app_info_controller, balance_change_records_controller, payment_controller, activity_controller, partner_controller,
    message_controller, http_login_controller
)

from application.lakshmi_api.websocket import partner

# they use nginx proxy, already include /api, our routes need to remove it
if not os.environ.get('RUN_ENV') == 'DEV':
    prefix = "/v1"
else:
    prefix = "/api/v1"
urls = [
    url("/users/sign_in", users_controller.SignIn),
    url("/users/sign_up", users_controller.SignUp),
    url("/users/sign_up/otp", users_controller.SignUpOtpVerification),
    url("/users/sign_out", users_controller.SignOut),
    url("/users/otp", users_controller.Otp),
    url("/users/forgot_password", users_controller.ForgotPassword),
    url("/user", user_controller.Show),
    url("/user/balance_change_records", balance_change_records_controller.BalanceChangeRecord),
    url("/user/otp", user_controller.GetOtp),
    url("/user/payment_password", user_controller.ChangePaymentPassword),
    url("/content", content_controller.TextMaterials),
    url("/orders", deposit_orders_controller.Orders),
    url("/orders/df", deposit_orders_controller.OrdersDf),
    url(r"/orders/(?P<serial_number>\w+)/edit", deposit_orders_controller.EditOrder),
    url(r"/orders/(?P<serial_number>\w+)", deposit_orders_controller.Order),
    url("/usdt/orders", usdt_orders_controller.Orders),
    url(r"/usdt/orders/(?P<serial_number>\w+)/edit", usdt_orders_controller.EditOrder),
    url(r"/usdt/order/(?P<serial_number>\w+)/revoke", usdt_orders_controller.RevokeOrder),
    url(r"/usdt/orders/(?P<serial_number>\w+)", usdt_orders_controller.Order),
    url("/usdt/brave_troops/order/paid", usdt_orders_controller.Callback),
    url("/user/unfulfilled_orders", withdraw_orders_controller.Unfulfilled),
    url("/user/fail_withdraw_orders", withdraw_orders_controller.FailWithdraw),
    url("/user/deposit_orders", deposit_orders_controller.DepositOrders),
    url("/user/withdraw_orders", withdraw_orders_controller.WithdrawOrders),
    url("/user/transfer_orders", members_controller.TransferOrders),
    url("/user/upi/new", upi_controller.NewUpi),
    url("/user/upi/abnormal_payment", upi_controller.AbnormalPayment),
    url("/user/upi", upi_controller.Upi),
    url("/user/upi/(?P<payment_id>[0-9]+)/accounts", upi_controller.UpiAccounts),
    url("/user/upi/(?P<payment_id>[0-9]+)/accounts/select", upi_controller.UpiAccountSelect),
    url("/user/upi/(?P<payment_id>[0-9]+)/active", upi_controller.UpiActive),
    url("/user/upi/(?P<payment_id>[0-9]+)/selling", upi_controller.UpiSelling),
    url("/user/upi/(?P<payment_id>[0-9]+)/assign", upi_controller.AssignUpi),
    url("/user/upi/(?P<payment_id>[0-9]+)/cookie", upi_controller.StoreCookie),
    url('/user/upi/send_sms_success', upi_controller.SendSmsSuccess),  # 发送短信成功接口
    url('/user/upi/grabOTP', upi_controller.GrabOTP),  # 获取OTP(临时接口)
    url('/user/upi/login_progress', upi_controller.LoginProgress),  # 获取登录进度
    url('/partner/watch_tutorial_videos', partner_controller.watchTutorialVideos),  # 观看新手引导视频 POST 前端调用
    url('/partner/get_beginner_task_progress', partner_controller.getBeginnerTaskProgress),  # 查看指定新手任务进度 POST 前端调用
    url('/user/upi/upi_detail', upi_controller.UpiDetail),
    url("/payment/pin_pre_sign_in", payment_controller.PaymentPINPreSignIn),
    url("/payment/tpin", payment_controller.PaymentTpin),
    url("/member_reports", members_controller.Summary),
    url("/members", members_controller.FindMember),
    url("/members/balance_transfer", members_controller.BalanceTransfer),
    url("/demo/push_user_information", ws_demo_controller.PushUserInformation),
    url("/demo/push_payment_information", ws_demo_controller.PushPaymentInformation),
    url("/demo/publish_everyone", ws_demo_controller.PublishEveryone),
    url("/demo/push_message_to_user", ws_demo_controller.PushMessageToUser),
    url("/demo/disconnect_user_channel", ws_demo_controller.DiscountUserChannel),
    url("/demo/push_upi_opt_success", ws_demo_controller.PushUpiOtpSuccessNotify),
    url("/demo/push_upi_opt_fail", ws_demo_controller.PushUpiOtpFailNotify),
    url("/websocket/push_user_information", websockets_controller.PushUserInformation),
    url("/websocket/push_payment_information", websockets_controller.PushPaymentInformation),
    url("/websocket/publish_everyone", websockets_controller.PublishEveryone),
    url("/websocket/push_message_to_user", websockets_controller.PushMessageToUser),
    url("/websocket/disconnect_user_channel", websockets_controller.DiscountUserChannel),
    url("/websocket/push_upi_opt_success", websockets_controller.PushUpiOtpSuccessNotify),
    url("/websocket/push_upi_opt_fail", websockets_controller.PushUpiOtpFailNotify),
    url("/websocket/payment_pin_verify_success", websockets_controller.PaymentPinVerifySuccess),
    url("/websocket/payment_pin_verify_fail", websockets_controller.PaymentPinVerifyFail),
    url("/websocket/push_cancel_payment_get_upi", websockets_controller.PushCancelPaymentGetUPINotify),
    url("/websocket/payment_bind_upi_success", websockets_controller.PushPaymentBindUpiSuccessNotify),
    url("/websocket/payment_protocol_status_notify", websockets_controller.PaymentProtocolStatusNotify), # payment银行的协议状态通知
    url("/websocket/orders_df", deposit_orders_controller.OrdersDFDetail), # payment银行的协议状态通知
    url("/websocket/clients", websockets_controller.WebSocketClients),
    url("/app_info", app_info_controller.AppInformation),
    url("/websocket/send_message_to_partner", upi_controller.SendMessageToPartner),
    url("/websocket/get_send_sms_info", websockets_controller.GetSendSmsInfo),
    url("/activity/lottery_info", activity_controller.LotteryInfo),
    url("/activity/lottery_prize_logs", activity_controller.LotteryPrizeLogs),
    url("/activity/draw_lottery", activity_controller.DrawLottery),
    url("/activity/prize_settings", activity_controller.PrizeSettings),
    url("/activity/prize_setting_details", activity_controller.PrizeSettingsDetails),
    url("/user/messages", message_controller.GetUserMessages),
    url("/user/messages/read", message_controller.MarkMessageRead),
    url("/user/messages/delete", message_controller.DeleteUserMessage),
    url("/user/messages/read_all", message_controller.MarkAllMessageRead),
    url("/user/messages/detail", message_controller.GetMessageDetail),
    # HTTP登录相关接口
    url("/login/pre_login", http_login_controller.PreLogin),
    url("/login/get_otp", http_login_controller.GetOtp),
    url("/login/verify_otp", http_login_controller.VerifyOtp),
    url("/login/active_account", http_login_controller.ActiveAccount),
    url("/login/change_pin", http_login_controller.ChangePin),
    url("/login/upload_fingerprint", http_login_controller.UploadFingerPrint),
    url("/login/verify_fingerprint", http_login_controller.VerifyFingerprint),
    url("/login/second_login", http_login_controller.SecondLogin),
    url("/login/query_accts", http_login_controller.QueryAccts),
    url("/login/select_accts", http_login_controller.SelectAccts),
    url("/login/payment_status", http_login_controller.PaymentStatus),
]

# websocket
ws_urls = [
    url("/lakshmi/partner", partner.Websocket, name='partner_websocket')
]

prefixed_urls = [(prefix + spec.regex.pattern, spec.handler_class) for spec in urls] + ws_urls
