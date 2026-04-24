from tornado.web import url

from application.merchant import merchant
from application.order import order
from application.login import login
from application.setting import channel, settingip, setting
from application.count import count

urls = [
    # 登录
    url("/login/singin", login.singIn, name='singIn'),
    url("/login/singout", login.singOut, name='singOut'),
    url("/login/getuserinfo", login.getUserInfo, name='getUserInfo'),
    # 统计
    url("/count/getcount", count.getCount, name='getCount'),
    url("/count/getcountonew", count.getCountOneW, name='getCountOneW'),
    url("/count/getbalancerecord", count.getBalanceRecord, name='getBalanceRecord'),
    # 订单管理
    url("/order/getorderds", order.getOrderDs, name='getOrderDs'),
    url("/order/getorderdf", order.getOrderDf, name='getOrderDf'),
    url("/order/adddf", order.addDf, name='addDf'),
    url("/order/adddfpl", order.addDfpl, name='addDfpl'),
    url("/order/getwithdraw", order.getWithdraw, name='getWithdraw'),
    url("/order/addwithdraw", order.addWithdraw, name='addWithdraw'),
    # 下级
    url("/merchant/getmerchant", merchant.getMerchant, name='getMerchant'),
    url("/merchant/addmerchant", merchant.addMerchant, name='addMerchant'),
    url("/merchant/updatemerchant", merchant.updateMerchant, name='updateMerchant'),
    url("/merchant/getmerchantchannel", merchant.getMerchatChannel, name='getMerchatChannel'),
    url("/merchant/updatemerchantchannel", merchant.updateMerchatChannel, name='updateMerchatChannel'),
    url("/merchant/getmerchantrank", merchant.getMerchantRank, name='getMerchantRank'),
    # 设置
    url("/setting/getchannel", channel.getChannel, name='getChannel'),
    url("/setting/getip", settingip.getIp, name='getIp'),
    url("/setting/updateip", settingip.updateIp, name='updateIp'),
    url("/setting/getinfo", setting.getInfo, name='getInfo'),
    url("/setting/checkgg", setting.checkGg, name='checkGg'),
    url("/setting/resetgg", setting.resetGg, name='resetGg'),
    url("/setting/resetpw", setting.resetPw, name='resetPw'),
]
