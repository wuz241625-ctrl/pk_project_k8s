msg = {
    # api相关
    0: {'code': 0, 'data': None, 'message': 'Operation failed'},
    20000: {'code': 20000, 'data': None, 'message': 'Operation successful'},
    10000: {'code': 10000, 'data': None, 'message': 'Illegal IP'},
    10001: {'code': 10001, 'data': None, 'message': 'Data format error'},
    10002: {'code': 10002, 'data': None, 'message': 'Parameter exception'},
    10003: {'code': 10003, 'data': None, 'message': 'Parameter cannot be empty'},
    10004: {'code': 10004, 'data': None, 'message': 'Merchant does not exist'},
    10005: {'code': 10005, 'data': None, 'message': 'Merchant status exception'},
    10006: {'code': 10006, 'data': None, 'message': 'Signature error'},
    10007: {'code': 10007, 'data': None, 'message': 'Frequent operations'},
    10008: {'code': 10008, 'data': None, 'message': 'Channel is busy'},
    10009: {'code': 10009, 'data': None, 'message': 'Gateway error'},
    10010: {'code': 10010, 'data': None, 'message': 'Channel maintenance'},
    10011: {'code': 10011, 'data': None, 'message': 'Amount error'},
    10012: {'code': 10012, 'data': None, 'message': 'Channel not activated'},
    10013: {'code': 10013, 'data': None, 'message': 'Rate error'},
    10014: {'code': 10014, 'data': None, 'message': 'Order failed'},
    10015: {'code': 10015, 'data': None, 'message': 'Insufficient payout balance'},
    10016: {'code': 10016, 'data': None, 'message': 'Order does not exist'},
    10017: {'code': 10017, 'data': None, 'message': 'IFSC error'},
    10018: {'code': 10018, 'data': None, 'message': 'Update UPI error'},
    10019: {'code': 10019, 'data': None, 'message': 'Bank record already exists'},
    10020: {'code': 10020, 'data': None, 'message': 'Update status error'},
    10021: {'code': 10021, 'data': None, 'message': 'Parsing failed'},
    10022: {'code': 10022, 'data': None, 'message': 'Payout setting exception'},
    10023: {'code': 10023, 'data': None, 'message': 'Merchant payout setting exception'},
    10024: {'code': 10024, 'data': None, 'message': 'Amount decimal is not zero'},
    10025: {'code': 10025, 'data': None, 'message': 'Duplicate UPI'},
    10026: {'code': 10026, 'data': None, 'message': 'Reconciliation locked, please try again later'},
    10027: {'code': 10027, 'data': None, 'message': 'Blacklist IP banned for collection'},
    10028: {'code': 10028, 'data': None, 'message': 'Blacklist user_id banned for collection'},
    10029: {'code': 10029, 'data': None, 'message': 'Transaction ID has been used'},
    10030: {'code': 10030, 'data': None, 'message': 'Transaction ID data format error'},
    10031: {'code': 10031, 'data': None, 'message': 'Payment Service Closed'},

    # 通用
    10100: {'type': 'system', 'code': 10100},  # 系统异常
    10101: {'type': 'system', 'code': 10101},  # 登录已过期
    10102: {'type': 'sendCode', 'code': 10102},  # 发送失败
    10103: {'type': 'sendCode', 'code': 10103},  # 发送失败
    # 登录
    10200: {'type': 'login.singIn', 'code': 10200},  # 登录成功
    10201: {'type': 'login.singIn', 'code': 10201},  # 账号或密码错误
    10202: {'type': 'login.singIn', 'code': 10202},  # 账号已被禁用
    10203: {'type': 'login.register', 'code': 10203},  # 账号已存在
    10204: {'type': 'login.register', 'code': 10204},  # 验证码错误
    10205: {'type': 'login.register', 'code': 10205},  # 注册成功
    10206: {'type': 'login.register', 'code': 10206},  # 注册失败
    10207: {'type': 'login.forget', 'code': 10207},  # 账号不存在
    10208: {'type': 'login.forget', 'code': 10208},  # 验证码错误
    10209: {'type': 'login.forget', 'code': 10209},  # 重置成功
    10210: {'type': 'login.forget', 'code': 10210},  # 重置失败
    10211: {'type': 'login.forget', 'code': 10211},  # 邀请码错误
    # 首页
    10300: {'type': 'home', 'code': 10300},
    10330: {'type': 'home.withdraw', 'code': 10330},  # 交易密码错误
    10331: {'type': 'home.withdraw', 'code': 10331},  # 余额不足
    10332: {'type': 'home.withdraw', 'code': 10332},  # 提现提交失败
    10333: {'type': 'home.withdraw', 'code': 10333},  # 提现提交成功
    10334: {'type': 'home.withdraw', 'code': 10334},  # 提现充值失败
    10335: {'type': 'home.withdraw', 'code': 10335},  # 提现充值成功

    # 代付
    10400: {'type': 'issue.snatch', 'code': 10400},  # 未认证
    10401: {'type': 'issue.snatch', 'code': 10401},  # 未激活
    10402: {'type': 'issue.snatch', 'code': 10402},  # 有未完成的订单
    10403: {'type': 'issue.snatch', 'code': 10403},  # 抢单失败
    10404: {'type': 'issue.snatch', 'code': 10404},  # 抢单成功
    10405: {'type': 'issue.confirmUpload', 'code': 10405},  # 上传失败
    10406: {'type': 'issue.confirmUpload', 'code': 10406},  # 上传成功
    10407: {'type': 'issue.snatch', 'code': 10407},  # 确认完成
    # 代理
    10500: {'type': 'agent.addagent', 'code': 10500},  # 账号已存在
    10501: {'type': 'agent.addagent', 'code': 10501},  # 新增成功
    10502: {'type': 'agent.addagent', 'code': 10502},  # 新增失败
    # 我的
    10600: {'type': 'my.payment', 'code': 10600},  # 账号已存在
    10601: {'type': 'my.payment', 'code': 10601},  # 新增成功
    10602: {'type': 'my.payment', 'code': 10602},  # 新增失败
    10603: {'type': 'my.payment', 'code': 10603},  # 启用禁用成功
    10604: {'type': 'my.payment', 'code': 10604},  # 启用禁用失败
    10605: {'type': 'my.payment', 'code': 10605},  # 删除成功
    10606: {'type': 'my.payment', 'code': 10606},  # 删除失败
    10607: {'type': 'my.payment', 'code': 10607},  # 有未处理的订单
    10608: {'type': 'my.payment', 'code': 10608},  # 启动中
    10609: {'type': 'my.payment', 'code': 10609},  # UPI已存在
    10610: {'type': 'my.payment', 'code': 10610},  # 手机号已存在
    10611: {'type': 'my', 'code': 10611},  # 密码错误
    10612: {'type': 'my', 'code': 10612},  # 验证码错误
    10613: {'type': 'my', 'code': 10613},  # 重置失败
    10614: {'type': 'my', 'code': 10614},  # 重置成功
    10615: {'type': 'my', 'code': 10615},  # 认证失败
    10616: {'type': 'my', 'code': 10616},  # 认证成功
    10617: {'type': 'my', 'code': 10617},  # 发送成功
    10618: {'type': 'my', 'code': 10618},  # 发送失败
    10619: {'type': 'my.payment', 'code': 10619},  # 接单开关设置失败
    10620: {'type': 'my.payment', 'code': 10620},  # 接单开启成功
    10621: {'type': 'my.payment', 'code': 10621},  # 接单关闭成功
    10622: {'type': 'my.payment', 'code': 10622},  # 账号不存在
    10623: {'type': 'my.payment', 'code': 10623},  # 编辑成功
    10624: {'type': 'my.payment', 'code': 10624},  # 编辑失败
    10625: {'type': 'my.payment', 'code': 10625},  # id不能为空
    10626: {'type': 'my.payment', 'code': 10626},  # 密码不能为空
    10627: {'type': 'my.payment', 'code': 10627},  # 网银id不能为空
}
msg_en = {
    # api相关
    0: {'code': 0, 'data': None, 'message': 'success'},
    10000: {'code': 10000, 'data': None, 'message': 'error'},
    10001: {'code': 10001, 'data': None, 'message': 'success'},
    10002: {'code': 10002, 'data': None, 'message': 'time_out'},
    10003: {'code': 10003, 'data': None, 'message': 'UTR already existed'},
    10004: {'code': 10004, 'data': None, 'message': 'UTR is valid'},
    10005: {'code': 10005, 'data': None, 'message': 'UTR refill failed.'},
    10006: {'code': 10006, 'data': None, 'message': 'Invalid parameters.'},
    10007: {'code': 10007, 'data': None, 'message': 'The parameters cannot be null'},
    10008: {'code': 10008, 'data': None, 'message': 'merchant ID is valid'},
    10009: {'code': 10009, 'data': None, 'message': 'sign error'},
    10010: {'code': 10010, 'data': None, 'message': 'UTR already upload'},
    10011: {'code': 10011, 'data': None, 'message': 'Failed to grab the lock, order is being processed, abort the operation'},
    10012: {'code': 10012, 'data': None, 'message': 'UTR submitted too frequently or already processing.'},
}
