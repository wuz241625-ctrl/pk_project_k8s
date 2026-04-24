from tornado.web import url

from application.recharge import recharge
from application.record import record
from application.record import easypaisa
from application.record import jazzcash
from application.merchant import merchant
from application.order import order,pub_acc_withdrawal,auto_payout
from application.partner import partner
from application.permissions import role, member
from application.login import login
from application.setting import channel, dsdf_lock, payment, settingip, other, vip, appsz, dfdiscount, message_handler,filters_data
from application.count import count,collect_partner
from application.usdtRecharge import usdtRecharge
from application.event import event, eventrule, evenlogs, event_pool, event_lottery_chance, even_beginner_process
from application.system import operationLog
urls = [
    # 登录
    url("/login/singin", login.singIn, name='singIn'),
    url("/login/singout", login.singOut, name='singOut'),
    url("/login/getuserinfo", login.getUserInfo, name='getUserInfo'),
    url("/login/getroutes", login.getRoutes, name='getRoutes'),
    # 统计
    url("/count/getcount", count.getCount, name='getCount'),
    url("/count/getcountonew", count.getCountOneW, name='getCountOneW'),
    url("/count/balance", count.getBalance, name='getBalance'),
    url("/count/daily", count.getDaily, name='getDaily'),
    url("/count/adminoperate", count.getAdmingoperate, name='getAdmingoperate'),
    url("/count/operate", count.getOperate, name='getOperate'),
    url("/count/getcollectpartner", collect_partner.getCollect, name='getCollect'),
    # url("/count/getpartner", collect_partner.getPartner, name='getCollect'),
    # url("/count/getOnlinePayment", collect_partner.getOnlinePayment, name='getOnlinePayment'),
    # 订单管理
    url("/order/getorderds", order.getOrderDs, name='getOrderDs'),
    url("/order/getDSMerchantFinishOrProcessing", order.getDSMerchantFinishOrProcessing, name='getDSMerchantFinishOrProcessing'),
    url("/order/handleorder", order.handleOrder, name='handleOrder'),
    url("/order/handleOrderFromThird", order.handleOrderFromThird, name='handleOrderFromThird'),
    url("/order/updateCdAudit", order.updateCd, name='updateCdAudit'),
    url("/order/updateCdConfirm", order.updateCd, name='updateCdConfirm'),
    url("/order/updateNoConfirm", order.updateCd, name='updateNoConfirm'),
    url("/order/getCdType", order.getCdType, name='getCdType'),
    # url("/order/addDsToCd", order.addDsToCd, name='addDsToCd'),  # 代收查单会导致商户掉线
    url("/order/getorderdscd", order.getOrderDsCd, name='getOrderDsCd'),
    url("/order/getDSCDProcessing", order.getDSCDProcessing, name='getDSCDProcessing'),
    url("/order/handlenotifyds", order.handleNotifyds, name='handleNotifyds'),
    url("/order/confirmSplitOrder", order.confirmSplitOrder, name='confirmSplitOrder'),
    url("/order/getorderdf", order.getOrderDf, name='getOrderDf'),
    url("/order/getOrderDfSplit", order.getOrderDfSplit, name='getOrderDfSplit'),
    url("/order/getDFMerchantFinishOrProcessing", order.getDFMerchantFinishOrProcessing, name='getDFMerchantFinishOrProcessing'),
    # url("/order/handleorderdf", order.handleOrderdf, name='handleOrderdf'),
    url("/order/handleOrderdfRevert", order.HandleOrderdfRevert, name='handleOrderdfRevert'),
    url("/order/handleOrderdfType1", order.HandleOrderdfType1, name='handleOrderdfType1'),
    url("/order/handleOrderdfType2", order.HandleOrderdfType2, name='handleOrderdfType2'),
    url("/order/handleOrderdfType3", order.HandleOrderdfType3, name='handleOrderdfType3'),
    url("/order/handleOrderdfType4", order.HandleOrderdfType4, name='handleOrderdfType4'),
    url("/order/handleBatchOrderdf", order.handleBatchOrderdf, name='handleBatchOrderdf'),
    url("/order/cancelorderdf", order.cancelOrderdf, name='cancelOrderdf'),
    url("/order/handlenotifydf", order.handleNotifydf, name='handleNotifydf'),
    url("/order/getThirdPays", order.getThirdPays, name='getThirdPays'),
    url("/order/handleBatchThirdpay", order.handleBatchThirdpay, name='handleBatchThirdpay'),
    url("/files/upload", order.upload, name='upload'),
    url("/order/saveHuizhi", order.saveHuizhi, name='saveHuizhi'),
    url("/order/uploadreceiptbatch", order.UploadReceiptBatch, name='upload_receipt_batch'),
    url("/order/exportOrderDfList", order.exportOrderDfList, name='exportOrderDfList'),
    url("/order/getBankTypeByPaymentId", order.getBankTypeByPaymentId, name='getBankTypeByPaymentId'),
    url("/order/importBankWithdrawal", pub_acc_withdrawal.importBankWithdrawal, name='importBankWithdrawal'),
    url("/order/getBankWithdrawal", pub_acc_withdrawal.getBankWithdrawal, name='getBankWithdrawal'),
    
    # 自动代付监控API
    url("/api/auto-payout/stats", auto_payout.auto_payout_stats, name='auto_payout_stats'),
    url("/api/auto-payout/orders", auto_payout.auto_payout_orders, name='auto_payout_orders'),
    url("/api/auto-payout/toggle", auto_payout.auto_payout_toggle, name='auto_payout_toggle'),
    url("/api/auto-payout/monitor", auto_payout.auto_payout_monitor, name='auto_payout_monitor'),
    url("/api/auto-payout/order-detail", auto_payout.auto_payout_order_detail, name='auto_payout_order_detail'),
    url("/api/auto-payout/payment-id-cooldown", auto_payout.auto_payout_payment_id_cooldown, name='auto_payout_payment_id_cooldown'),
    url("/api/auto-payout/order-cooldown-config", auto_payout.auto_payout_order_cooldown_config, name='auto_payout_order_cooldown_config'),
    
    # 提现转账
    # url("/recharge/getsystemcard", recharge.getSystemCard, name='getSystemCard'),
    url("/recharge/getrechargepartner", recharge.getRechargePartner, name='getRechargePartner'),
    url("/recharge/getStaticsReport", recharge.getStaticsReport, name='getStaticsReport'),
    url("/recharge/addStaticsReport", recharge.addStaticsReport, name='addStaticsReport'),
    url("/recharge/deleteStaticsReport", recharge.deleteStaticsReport, name='deleteStaticsReport'),
    url("/recharge/handlerechargepartner", recharge.handleRechargePartner, name='handleRechargePartner'),
    # url("/recharge/getrechargemerchant", recharge.getRechargeMerchant, name='getRechargeMerchant'),
    # url("/recharge/handlerechargemerchant", recharge.handleRechargeMerchant, name='handleRechargeMerchant'),
    url("/recharge/getwithdrawpartner", recharge.getWithdrawPartner, name='getWithdrawPartner'),
    url("/recharge/handlewithdrawpartner", recharge.handleWithdrawPartner, name='handleWithdrawPartner'),
    url("/recharge/getwithdrawmerchant", recharge.getWithdrawMerchant, name='getWithdrawMerchant'),
    url("/recharge/handlewithdrawmerchant", recharge.handleWithdrawMerchant, name='handleWithdrawMerchant'),

    url("/usdtRecharge/getUsdtRechargePartner", usdtRecharge.getUsdtRecharge, name='getUsdtRecharge'),
    url("/usdtRecharge/handleUsdtRechargePartner", usdtRecharge.handleUsdtRechargePartner, name='handleUsdtRechargePartner'),

    # 资金流水
    url("/record/getsysrecord", record.getSysRecord, name='getSysRecord'),
    url("/record/getbalancerecord", record.getBalanceRecord, name='getBalanceRecord'),
    
    # EasyPaisa相关接口
    url("/record/easypaisa/getaccountlist", easypaisa.getAccountList, name='getEasyPaisaAccountList'),
    url("/record/easypaisa/downloadbill", easypaisa.downloadBill, name='downloadEasyPaisaBill'),
    
    # JazzCash相关接口
    url("/record/jazzcash/getaccountlist", jazzcash.getAccountList, name='getJazzCashAccountList'),
    url("/record/jazzcash/querybill", jazzcash.queryBill, name='queryJazzCashBill'),
    # # 商户
    url("/merchant/getmerchant", merchant.getMerchant, name='getMerchant'),
    url("/merchant/addmerchant", merchant.addMerchant, name='addMerchant'),
    url("/merchant/updatemerchant", merchant.updateMerchant, name='updateMerchant'),
    url("/merchant/getmerchantchannel", merchant.getMerchatChannel, name='getMerchatChannel'),
    url("/merchant/updatemerchantchannel", merchant.updateMerchatChannel, name='updateMerchatChannel'),
    url("/merchant/resetggkey", merchant.resetGgkey, name='resetGgkey'),
    url("/merchant/getmerchantrank", merchant.getMerchantRank, name='getMerchantRank'),
    url("/merchant/getmerchantsuccessrate", merchant.getMerchantSuccessRate, name='getMerchantSuccessRate'),
    # 码商
    url("/partner/export", partner.exportPartner, name='exportPartner'),
    url("/partner/getpartner", partner.getPartner, name='getPartner'),
    url("/partner/getMigrate", partner.getMigrate, name='getMigrate'),
    url("/partner/migratePartner", partner.migratePartner, name='migratePartner'),  # 迁移码商
    url("/partner/updatepartner", partner.updatePartner, name='updatePartner'),
    url("/partner/updatePartnerUnlock", partner.updatePartner, name='updatePartnerUnlock'),
    url("/partner/updatePartnerLock", partner.updatePartner, name='updatePartnerLock'),
    url("/partner/addpartner", partner.addPartner, name='addPartner'),
    url("/partner/getpartnerrank", partner.getPartnerRank, name='getPartnerRank'),
    url("/partner/getpayment", partner.getPayment, name='getPayment'),
    url("/partner/getchannel", partner.getChannel, name='getChannel'),
    url("/partner/updatepayment", partner.updatePayment, name='updatePayment'),
    url("/partner/updatePaymentMonitorStatus", partner.updatePaymentMonitorStatus, name='updatePaymentMonitorStatus'),
    url("/partner/updatePaymentLimit", partner.updatePayment, name='updatePaymentLimit'),
    url("/partner/updatePaymentReject", partner.updatePayment, name='updatePaymentReject'),
    url("/partner/updatePaymentPass", partner.updatePayment, name='updatePaymentPass'),
    url("/partner/updatePaymentDisenable", partner.updatePayment, name='updatePaymentDisenable'),
    url("/partner/updatePaymentEnable", partner.updatePayment, name='updatePaymentEnable'),
    url("/partner/updatePaymentLock", partner.updatePayment, name='updatePaymentLock'),
    url("/partner/updatePaymentUnlock", partner.updatePayment, name='updatePaymentUnlock'),
    url("/partner/updatePaymentCorrection", partner.updatePayment, name='updatePaymentCorrection'),
    url("/partner/updatePaymentCommon", partner.updatePayment, name='updatePaymentCommon'),
    url("/partner/updatePaymentPri", partner.updatePayment, name='updatePaymentPri'),
    url("/partner/updatePaymentEdit", partner.updatePayment, name='updatePaymentEdit'),
    url("/partner/uploadBankStatement", partner.uploadBankStatement, name='uploadBankStatement'),
    url("/partner/importBankRecord", partner.importBankRecord, name='importBankRecord'),
    url("/partner/handleClearBalance", partner.handleClearBalance, name='handleClearBalance'),
    url("/partner/addpayment", partner.addpayment, name='addpayment'),
    url("/partner/deletepayment", partner.deletePayment, name='deletePayment'),
    url("/partner/getbank_type", partner.getBank_type, name='getBank_type'),
    url("/partner/getbank_recoed", partner.getBank_recoed, name='getBank_recoed'),
    url("/partner/addbank_recoed", partner.addBank_recoed, name='addBank_recoed'),
    url("/partner/delbank_recoed", partner.delBank_recoed, name='delBank_recoed'),
    url("/partner/get_phonepe", partner.get_Phonepe, name='get_Phonepe'),
    url("/partner/add_phonepe", partner.add_Phonepe, name='add_Phonepe'),
    url("/partner/update_phonepe", partner.update_Phonepe, name='update_Phonepe'),
    url("/partner/del_phonepe", partner.del_Phonepe, name='del_Phonepe'),
    url("/partner/resettingPayment", partner.resettingPayment, name='resettingPayment'),
    url("/partner/batchDisablePayment", partner.batchDisablePayment, name='resettingPayment'),  # 收款资料批量禁用
    url("/partner/getBankType", partner.getBankType, name='getBankType'),  # 银行管理查询
    url("/partner/getBankTypeSetting", partner.getBankTypeSetting, name='getBankTypeSetting'),
    url("/partner/updateBankTypeStatus", partner.updateBankTypeStatus, name='updateBankTypeStatus'),  # 银行管理修改状态
    url("/partner/updateBankTypeStatusSetting", partner.updateBankTypeStatusSetting, name='updateBankTypeStatusSetting'),
    url("/partner/updateBankType", partner.updateBankType, name='updateBankType'),  # 银行管理编辑
    url("/partner/updateBankTypeSetting", partner.updateBankTypeSetting, name='updateBankTypeSetting'),
    url("/partner/addBankType", partner.addBankType, name='addBankType'),  # 银行管理添加
    url("/partner/addBankTypeSetting", partner.addBankTypeSetting, name='addBankTypeSetting'), 
    # url("/partner/deleteBankType", partner.deleteBankType, name='deleteBankType'),  # 银行管理删除
    url("/partner/getBankRank", partner.getBankRank, name='getBankRank'), # 银行排名
    url("/partner/cancelLimit", partner.cancelLimit, name='cancelLimit'),  # 取消限制
    url("/partner/getSms", partner.GetSms, name='getSms'),  # 短信列表

    # 码商转账
    url("/partner/createtransfer", partner.createTransfer, name='createTransfer'),
    url("/partner/gettransfer", partner.getTransfer, name='getTransfer'),
    url("/partner/handletransfer", partner.handleTransfer, name='handleTransfer'),
    # 通道设置
    url("/setting/switchPaymentServiceState", channel.switchPaymentServiceState, name='switchPaymentServiceState'),
    url("/setting/getPaymentServiceState", channel.getPaymentServiceState, name='getPaymentServiceState'),
    url("/setting/switchJazzCashPayoutServiceState", channel.switchJazzCashPayoutServiceState, name='switchJazzCashPayoutServiceState'),
    url("/setting/getJazzCashPayoutServiceState", channel.getJazzCashPayoutServiceState, name='getJazzCashPayoutServiceState'),
    url("/setting/getotherpay", channel.getOtherPay, name='getOtherPay'),
    url("/setting/getchannel", channel.getChannel, name='getChannel'),
    url("/setting/changeotherpay", channel.changeOtherPay, name='changeOtherPay'),
    url("/setting/updatechannel", channel.updateChannel, name='updateChannel'),
    url("/setting/testorder", channel.testOrder, name='testOrder'),
    # 代收代付配置
    url("/setting/getDSSettings", channel.getDSSettings, name='getDSSettings'),
    url("/setting/addDSSettings", channel.addDSSettings, name='addDSSettings'),
    url("/setting/delDSSettings", channel.delDSSettings, name='delDSSettings'),
    url("/setting/edtDSSettings", channel.edtDSSettings, name='edtDSSettings'),
    url("/setting/getDFSettings", channel.getDFSettings, name='getDFSettings'),
    url("/setting/addDFSettings", channel.addDFSettings, name='addDFSettings'),
    url("/setting/delDFSettings", channel.delDFSettings, name='delDFSettings'),
    url("/setting/edtDFSettings", channel.edtDFSettings, name='edtDFSettings'),
    # 条件配置
    url("/setting/filtersAddOrUpdate", filters_data.filtersAddOrUpdate, name='filtersAddOrUpdate'),
    url("/setting/getFilters", filters_data.getFilters, name='getFilters'),
    # app设置
    url("/setting/getappsz", appsz.getAppsz, name='getAppsz'),
    url("/setting/updateappsz", appsz.updateAppsz, name='updateAppsz'),
    # 代付优惠
    url("/setting/getdfdiscount", dfdiscount.getDfDiscount, name='getDfDiscount'),
    url("/setting/updatedfdiscount", dfdiscount.updateDfDiscount, name='updateDfDiscount'),
    url("/setting/getUsdtDfDiscount", dfdiscount.getUsdtDfDiscount, name='getUsdtDfDiscount'),
    url("/setting/updateUsdtDfdiscount", dfdiscount.updateUsdtDfdiscount, name='updateUsdtDfdiscount'),
    # IP设置
    url("/setting/getip", settingip.getIp, name='getIp'),
    url("/setting/updateip", settingip.updateIp, name='updateIp'),
    # 系统收款信息
    url("/setting/getpayment", payment.getPayment, name='getpayment'),
    url("/setting/addpayment", payment.addPayment, name='addPayment'),
    url("/setting/updatepayment", payment.updatePayment, name='updatepayment'),
    url("/setting/deletepayment", payment.deletePayment, name='deletepayment'),
    # VIP设置
    url("/setting/getvip", vip.getVip, name='getVip'),
    url("/setting/updatevip", vip.updateVip, name='updateVip'),
    # IP其他设置
    url("/setting/getother", other.getOther, name='getOther'),
    url("/setting/updateother", other.updateOther, name='updateOther'),
    url("/setting/getweight", other.getWeight, name='getWeight'),
    url("/setting/updateweight", other.updateWeight, name='updateWeight'),
    url("/setting/getUsdtTransferAddress", other.getUsdtTransferAddress, name='updateUsdtTransferAddress'),
    url("/setting/updateUsdtTransferAddress", other.updateUsdtTransferAddress, name='updateUsdtTransferAddress'),
    # 代收代付锁定设置
    url("/setting/getDsdfLockSettings", dsdf_lock.GetDsdfLock, name='getDsdfLock'),
    url("/setting/updateDsdfLockSettings", dsdf_lock.UpdateDsdfLock, name='updateDsdfLock'),
    # 商户支付链接
    url("/setting/MerchantPayLinks", other.MerchantPayLinks, name='MerchantPayLinks'),
    # 用户管理
    url("/member/getmember", member.getMember, name='getMember'),
    url("/member/addmember", member.addMember, name='addMember'),
    url("/member/updatemember", member.updateMember, name='updateMember'),
    url("/member/deletemember", member.deleteMember, name='deleteMember'),
    url("/member/resetggkey", member.resetGgkey, name='resetggkey'),
    # 角色管理
    url("/role/getpermissions", role.getPermissions, name='getPermissions'),
    url("/role/getrole", role.getRole, name='getRole'),
    url("/role/addrole", role.addRole, name='addRole'),
    url("/role/updaterole", role.updateRole, name='updateRole'),
    url("/role/deleterole", role.deleteRole, name='deleteRole'),
    url("/role/getCurrentUserRole", role.getCurrentUserRole, name='getCurrentUserRole'),
    url("/role/getCurrentUserRolePermissions", role.getCurrentUserRolePermissions, name='getCurrentUserRolePermissions'),
    # 活动管理
    url("/event/getevent", event.getEvent, name='getEvent'),
    url("/event/addevent", event.addevent, name='addevent'),
    url("/event/updateevent", event.updateevent, name='updateevent'),
    url("/event/deleteevent", event.deleteevent, name='deleteevent'),
    # 活动明细配置
    url("/eventrule/getEventrule", eventrule.getEventrule, name='getEventrule'),
    url("/eventrule/addeventrule", eventrule.addeventrule, name='addeventrule'),
    url("/eventrule/updateeventrule", eventrule.updateeventrule, name='updateeventrule'),
    url("/eventrule/deleteeventrule", eventrule.deleteeventrule, name='deleteeventrule'),
    # 活动奖励日志查询
    url("/eventlogs/getEventLogs", evenlogs.getEventLogs, name='getEventLogs'),
    # 抽奖活动奖池
    url("/event/getPoolAmount", event_pool.getPoolAmount, name='getPoolAmount'),
    url("/event/getPoolLogs", event_pool.getPoolLogs, name='getPoolLogs'),
    url("/event/addPoolAmount", event_pool.addPoolAmount, name='addPoolAmount'),

    url("/event/getLotteryChance", event_lottery_chance.getLotteryChance, name='getLotteryChance'),
    url("/event/getLotteryChanceLog", event_lottery_chance.getLotteryChanceLog, name='getLotteryChanceLog'),
    url("/event/addLotteryChance", event_lottery_chance.addLotteryChance, name='addLotteryChance'),
    # 新手活动
    url("/event/getEventBeginnerProcess", even_beginner_process.getEventBeginnerProcess, name='getEventBeginnerProcess'),

    # 站内信管理
    url("/message/add", message_handler.AddMessage, name='addMessage'),
    url("/message/delete", message_handler.DeleteMessage, name='deleteMessage'),
    url("/message/list", message_handler.GetMessages, name='getMessages'),
    url("/message/publish", message_handler.PublishMessage, name='publishMessage'),
    url("/message/update", message_handler.UpdateMessage, name='updateMessage'),

    url("/system/operationlog", operationLog.IOperationLog, name='operationLogCUDA')

]
