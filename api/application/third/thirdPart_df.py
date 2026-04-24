import decimal
import random
import string
import time
import uuid
import hashlib
from urllib.parse import urlencode

from requests.auth import HTTPBasicAuth

from application.sign import SignatureAndVerification
import requests
import simplejson as json
from urllib.parse import urlparse
from config import get_config

def AGDF(rds, logging, data, mer_id, mer_key, pay_url):
    # AG代付
    # notify = self.reverse_url('notice_XLZZF_df_Pay')
    notify = "/df_notice/AGDF"

    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]
        # host = "https://c.ipay268.cc"
        data_post = dict()
        data_post['clientCode'] = mer_id
        data_post['chainName'] = "BANK"
        data_post['coinUnit'] = "INR"
        data_post['bankCardNum'] = data['payment_account']
        data_post['bankUserName'] = data['payment_name']
        data_post['ifsc'] = data['ifsc']
        data_post['bankName'] = data['payment_bank']
        data_post['amount'] = int(decimal.Decimal(data['amount']))
        data_post['clientNo'] = data['code']
        data_post['requestTimestamp'] = int(round(time.time() * 1000))
        data_post['callbackurl'] = host + notify
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key, "AGDF")
        data_post['sign'] = data_post['sign'].lower()
        logging.info('notice_AGDF_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, timeout=(5,10), verify=False)
        logging.info('AG代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if ret['success'] is True:
            logging.error('notice_AGDF_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_AGDF_Pay 订单-{code}-失败'.format(code= data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_AGDF_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def cubpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # cubpay代付
    # notify = self.reverse_url('notice_XLZZF_df_Pay')
    notify = "/df_notice/cubpay"

    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]
        # host = "https://c.ipay268.cc"
        data_post = dict()
        data_post['UserId'] = mer_id
        data_post['apikey'] = mer_key
        data_post['Amount'] = decimal.Decimal(data['amount'])
        data_post['AccountNo'] = data['payment_account']
        data_post['IFSC'] = data['ifsc']
        data_post['SenderMobile'] = "9999999999"
        data_post['SenderName'] = data['payment_name']
        data_post['SenderEmail'] = "abc@abc.com"
        data_post['BeneName'] = data['payment_name']
        data_post['BeneMobile'] = "8888888888"
        data_post['OrderId'] = data['code']
        data_post['SPKey'] = "IMPS"
        data_post = json.dumps(data_post, separators=(',', ':'))
        logging.info('notice_AGDF_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json, text/javascript',
            'Content-Type': 'application/json',
        }
        # 时间长
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(30,30), verify=False)
        logging.info('cubpay代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)[0]

        if 'Success' in ret.keys() and ret['Success'] == "0":  # 失败
            logging.error('notice_CUB_Pay 订单-{code}-失败'.format(code=data['code']))
            return False

        if ret['status'] == "1":  # 成功
            if not ret['OrderId'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['transaction_id'], data['code']))
                logging.error('notice_CUB_Pay 订单-{code}-{third_code} 成功'.format(code=data['code'], third_code=ret['transaction_id']))
            logging.info('notice_CUB_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        elif ret['status'] == "2":  # 失败
            logging.error('notice_CUB_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
        elif ret['status'] == "0":  # pending
            logging.info('notice_CUB_Pay 订单-{code}-pending 成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_CUB_Pay 订单-{code}-失败'.format(code= data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_CUB_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_CUB_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def wallet(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # walletflow代付
    # notify = self.reverse_url('notice_XLZZF_df_Pay')
    # notify = "/api/df_notice/walletflow"
    notify = "/df_notice/walletflow"

    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]
        # host = "https://c.ipay268.cc"
        # host = "https://sunnyboy.ipay268.cc"
        data_post = dict()
        data_post['secret_key'] = mer_key
        data_post['amount'] = str(int(data['amount']))
        data_post['mode'] = "IMPS"
        data_post['account'] = data['payment_account']
        data_post['ifsc'] = data['ifsc']
        data_post['name'] = data['payment_name']
        data_post['remark'] = data['code']
        data_post = json.dumps(data_post, separators=(',', ':'))
        logging.info('notice_WALLET_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        # 时间长
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(30,30), verify=False)
        logging.info('wallet代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        if 'status' in ret.keys() and ret['status'] == False:  # 失败
            logging.error('notice_WALLET_Pay 订单-{code}-失败'.format(code=data['code']))
            return False

        if ret['data']['success'] == True:  # 成功
            if ret['data']['data']['status'] == "Failed":  # 失败 除去失败以外的其他三种状态默认为创建订单成功 Received,InProgress,Completed
                logging.error('notice_WALLET_Pay 订单-{code}-失败-{message}'.format(code=data['code'],message=ret['data']['message'] ))
                return False
            if not ret['data']['data']['orderId'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['data']['data']['orderId'], data['code']))
                logging.info('notice_WALLET_Pay 订单-{code}-{third_code} 成功-{message}-{status}'.format(code=data['code'], third_code=ret['data']['data']['orderId'],message=ret['data']['message'],status=ret['data']['data']['status']))
                return True
        else:
            logging.error('notice_WALLET_Pay 订单-{code}-失败-{message}'.format(code= data['code'],message=ret['data']['message']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_WALLET_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_WALLET_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def haoda(cur, rds, logging, data, mer_id, mer_key, pay_url, mer_key2):
    """Haoda代付"""
    try:
        data_post = dict()
        data_post.update({
            "account_number": data['payment_account'],
            "account_ifsc": data['ifsc'],
            "bankname": data['payment_bank'],
            "confirm_acc_number": data['payment_account'],
            "requesttype": "IMPS",
            "beneficiary_name": data['payment_name'],
            "amount": decimal.Decimal(data['amount']),
            "narration": "Test bank transaction",
            "reference": data['code']
        })
        data_post = json.dumps(data_post)
        logging.info('notice_Haoda_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'x-client-id': mer_id,
            'x-client-secret': mer_key,
        }
        proxies = {
            'http': mer_key2,
            'https': mer_key2
        }
        # 请求
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(30, 30), verify=False, proxies=proxies)
        logging.info('Haoda代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(
            code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        if str(ret['status_code']) == '200':  # 成功
            if not ret['payout_id'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['payout_id'], data['code']))
                logging.info('notice_Haoda_Pay 订单-{code}-{third_code} 成功-{message}-{status}'.format(
                    code=data['code'], third_code=ret['payout_id'], message=ret['message'],
                    status=ret['status']))
            return True
        else:  # 失败
            logging.error('notice_Haoda_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_Haoda_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(
            code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_Haoda_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(
            code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def happypay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # happypay代付
    notify = "/df_notice/happypay"

    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['username'] = mer_id
        data_post['amount'] = str(decimal.Decimal(data['amount']))
        data_post['order_number'] = data['code']
        data_post['notify_url'] = host + notify
        data_post['bank_card_holder_name'] = data['payment_name']
        data_post['bank_card_number'] = data['payment_account']
        data_post['bank_name'] = data['payment_bank']
        data_post['bank_ifsc'] = data['ifsc']
        data_post['bank_phone'] = "18602667777"
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key, "secret_key")
        data_post['sign'] = data_post['sign'].lower()
        logging.info('notice_Happy_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, timeout=(5,10), verify=False)
        logging.info('Happy代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        # 200或201都是成功
        if ret["http_status_code"] == 200 or ret["http_status_code"] == 201:  # 成功
            if not ret['data']['system_order_number'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['data']['system_order_number'], data['code']))
                logging.info('notice_Happy_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(code=data['code'], third_code=ret['data']['system_order_number'], message=ret['message'],status=ret['http_status_code'],data=ret['data']))
            logging.info('notice_Happy_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_Happy_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_Happy_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_Happy_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def kingpay(cur, rds, logging, data, mer_id, mer_key, pay_url, mer_key3, notify):
    # kingpay代付
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['merchantId'] = mer_id
        data_post['appId'] = mer_key
        data_post['withdrawAmount'] = str(decimal.Decimal(data['amount']))
        data_post['outOrderId'] = data['code']
        data_post['notifyUrl'] = host + notify
        data_post['accountName'] = data['payment_name'].replace(' ', '')
        data_post['cardNumber'] = data['payment_account']
        data_post['bankName'] = data['payment_bank'].replace(' ', '')
        data_post['bankCode'] = data['ifsc']
        data_post['bankSubbranch'] = data['ifsc']
        data_post['payeePhone'] = "18602667777"
        data_post['timestamp'] = int(round(time.time() * 1000))
        data_post['sign'] = SignatureAndVerification.sha256_sign(data_post, mer_key3)

        data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        logging.info('notice_King_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10))
        logging.info('King代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        # code 0	成功
        if ret["code"] == '0':  # 成功
            if not ret['orderId'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['orderId'], data['code']))
                logging.info('notice_King_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(code=data['code'], third_code=ret['orderId'], message=ret['statusDesc'],status=ret['status'],data=ret))
            logging.info('notice_King_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_King_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_King_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_King_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def razo(cur, rds, logging, data, mer_id, mer_key, pay_url, mer_key2):
    """
    Razo代付
    创建此代付订单，分为3步：
    1.获取contacts(联系人)，没有则需创建
    2.根据contacts获取Fund Accounts(资金账户)，没有则需创建
    3.用Fund Accounts获取到的fund_account_id请求代付
    """
    try:
        api_key = mer_id
        api_secret = mer_key
        # 1.获取contacts(联系人)，没有则需创建
        url = 'https://api.razorpay.com/v1/contacts'
        contact_name = '{}_{}'.format(data['payment_name'], data['payment_account'])  # 用支付名和卡号组成唯一联系人标识
        params = {'name': contact_name}
        res = requests.get(url, params=params, auth=HTTPBasicAuth(api_key, api_secret))
        res_data = res.json()
        if res_data.get('items'):
            contact_id = res_data['items'][0].get('id')
        else:
            data_post = {'name': contact_name}
            headers = {'Content-Type': 'application/json'}
            res = requests.post(
                url, auth=HTTPBasicAuth(api_key, api_secret),
                json=data_post, headers=headers)
            logging.info('Razo代付创建联系人-{code}-发送地址{url},发送{data_post},结果{ret}'.format(
                code=data['code'], url=url, data_post=data_post, ret=res.text))
            contact_id = res.json().get('id')

        # 2.根据contacts获取Fund Accounts(资金账户)，没有则需创建
        url = 'https://api.razorpay.com/v1/fund_accounts'
        params = {'contact_id': contact_id}
        res = requests.get(url, params=params, auth=HTTPBasicAuth(api_key, api_secret))
        res_data = res.json()
        if res_data.get('items'):
            fund_account_id = res_data['items'][0].get('id')
        else:
            data_post = {
                "contact_id": contact_id,
                "account_type": "bank_account",
                "bank_account": {
                    "name": data['payment_name'],
                    "ifsc": data['ifsc'],
                    "account_number": data['payment_account']
                }
            }
            headers = {'Content-Type': 'application/json'}
            res = requests.post(url, auth=HTTPBasicAuth(api_key, api_secret), json=data_post, headers=headers)
            logging.info('Razo代付创建资金账户-{code}-发送地址{url},发送{data_post},结果{ret}'.format(
                code=data['code'], url=pay_url, data_post=data_post, ret=res.text))
            fund_account_id = res.json().get('id')

        # 3.用Fund Accounts获取到的fund_account_id请求代付
        data_post = dict()
        data_post['account_number'] = mer_key2
        data_post['fund_account_id'] = fund_account_id
        data_post['amount'] = int(decimal.Decimal(data['amount']) * 100)   # 传入的金额单位是Paise(分)，需要用 卢比 乘以100
        data_post['currency'] = 'INR'
        data_post['mode'] = 'IMPS'
        data_post['purpose'] = 'payout'
        data_post['queue_if_low_balance'] = False  # True：余额不足时挂起 / False：余额不足时支付失败
        data_post['reference_id'] = data['code']
        logging.info('notice_Razo_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        headers = {
            'Content-Type': 'application/json',
            'X-Payout-Idempotency': str(uuid.uuid4()),
        }
        # 请求
        r = requests.post(pay_url, auth=HTTPBasicAuth(api_key, api_secret), json=data_post, headers=headers)
        logging.info('Razo代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(
            code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = r.json()

        if ret.get('status'):  # 成功
            if ret.get('id', ''):  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['id'], data['code']))
                logging.info('notice_Razo_Pay 订单-{code}-{third_code} 成功-{message}-{status}'.format(
                    code=data['code'], third_code=ret['id'], message=ret['narration'],
                    status=ret['status']))
            return True
        else:  # 失败
            logging.error('notice_Razo_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_Razo_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(
            code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_Razo_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(
            code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def ydpay(cur, rds, logging, data, mer_id, mer_key, pay_url, mer_key2):
    # ydpay代付
    notify = "/df_notice/ydpay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['merchant_id'] = mer_id
        data_post['order_amount'] = str(decimal.Decimal(data['amount']))
        data_post['email'] = "vanhimus@gmail.com"
        data_post['bank_user_name'] = data['payment_name']
        data_post['bank_number'] = data['payment_account']
        data_post['bank_ifsc'] = data['ifsc']
        data_post['mobile'] = '8968500155'
        data_post['notify_url'] = host + notify
        data_post['merchant_order_no'] = data['code']

        data_post['sign'] = SignatureAndVerification.md5_sign2(data_post, mer_key)

        # data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        # 获取到mer_key2(代理)则组装代理参数
        proxies = None
        if mer_key2:
            proxies = {
                'http': mer_key2,
                'https': mer_key2
            }
        logging.info('notice_YD_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=json.dumps(data_post)))
        r = requests.post(pay_url, json=data_post, headers=headers, timeout=(5,10), verify=False, proxies=proxies)
        logging.info('YDPay代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=json.dumps(data_post), ret=r.text))
        ret = json.loads(r.text)

        # status success	成功
        if ret["status"] == 'success':  # 成功
            if not ret['data']['order_no'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['data']['order_no'], data['code']))
                logging.info('notice_YD_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(code=data['code'], third_code=ret['data']['order_no'], message=ret['message'],status=ret['status'],data=ret))
            logging.info('notice_YD_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_YD_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_YD_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_YD_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def sdpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # sdpay代付
    notify = "/df_notice/sdpay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['id'] = mer_id
        data_post['flags'] = '103'
        data_post['order_no'] = data['code']
        data_post['amount'] = str(int(data['amount']))
        data_post['payee_name'] = data['payment_name']
        data_post['payee_bank_name'] = data['payment_bank']
        data_post['payee_bank_code'] = data['ifsc']
        data_post['payee_account'] = data['payment_account']
        data_post['callback_url'] = host + notify

        # 参与签名参数严格按照此顺序:1.payee_bank_code, 2.payee_bank_name, 3.payee_account,
        # 4.payee_name, 5.amount, 6.flags, 7.id, 8.order_no, 9.callback_url, 10.商户密钥
        sign_fields_sort_list = ['payee_bank_code', 'payee_bank_name', 'payee_account', 'payee_name', 'amount',
                                 'flags', 'id', 'order_no', 'callback_url']
        sign_data_list = [data_post[i] for i in sign_fields_sort_list]
        sign_data_list.append(mer_key)
        sign_data_str = '|'.join(sign_data_list)
        data_post['sign'] = SignatureAndVerification.get_md5_str(sign_data_str)

        # data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        logging.info('notice_SD_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10))
        logging.info('SD代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        # status True	成功
        if ret["status"]:  # 成功
            if not ret['data']['ref_no'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['data']['ref_no'], data['code']))
                logging.info('notice_SD_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(code=data['code'], third_code=ret['data']['ref_no'], message=ret['data']['ref_no'],status=ret['status'],data=ret))
            logging.info('notice_SD_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_SD_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_SD_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_SD_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def queen(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # queen代付
    notify = "/df_notice/queen"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['merchant'] = mer_id
        data_post['total_amount'] = data['amount']
        data_post['callback_url'] = host + notify
        data_post['order_id'] = data['code']
        data_post['bank'] = data['ifsc'][:5].upper()
        data_post['bank_card_name'] = data['payment_name']
        data_post['bank_card_account'] = data['payment_account']
        data_post['bank_card_remark'] = data['ifsc']

        data_post['sign'] = SignatureAndVerification.md5_sign2(data_post, mer_key)

        data_post_json = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        logging.info('notice_QUEEN_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post_json))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10))
        logging.info('QUEEN代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post_json, ret=r.text))
        ret = json.loads(r.text)

        # status 1	成功
        if str(ret["status"]) == '1':  # 成功
            # 无第三方订单号，不需保存
            logging.info('notice_QUEEN_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_QUEEN_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_QUEEN_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_QUEEN_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def inpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # inpay代付
    notify = "/df_notice/inpay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['client_id'] = mer_id
        data_post['bill_number'] = data['code']
        data_post['type'] = '00'  # 00: 纯代付 01: 卡卡 02: UPI
        data_post['amount'] = int(data['amount'])
        data_post['receiver_name'] = data['payment_name']
        data_post['receiver_account'] = data['payment_account']
        data_post['bank'] = data['payment_bank']
        data_post['bank_branch'] = 'N/A'
        data_post['notify_url'] = host + notify
        data_post['remark'] = data['ifsc']

        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key).lower()

        data_post = json.dumps(data_post)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        logging.info('notice_IN_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10))
        logging.info('IN_Pay代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        # code 0	成功
        if str(ret["code"]) == '0':  # 成功
            if not ret['system_bill_number'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['system_bill_number'], data['code']))
                logging.info('notice_SD_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(code=data['code'], third_code=ret['system_bill_number'], message=ret.get('message'),status=ret['status'],data=ret))
            logging.info('notice_IN_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_IN_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_IN_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_IN_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def redpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # redpay代付
    notify = "/df_notice/redpay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['mchid'] = mer_id
        data_post['out_trade_no'] = data['code']
        data_post['money'] = data['amount']
        data_post['bankcode'] = data['ifsc']
        data_post['bankname'] = data['payment_bank']
        data_post['accountname'] = data['payment_name']
        data_post['cardnumber'] = data['payment_account']
        data_post['notifyurl'] = host + notify

        data_post['pay_md5sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                          'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            # 'Content-Type': 'application/json'
        }
        logging.info('notice_RED_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10))
        logging.info('RED_Pay代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        # code 0	成功
        if str(ret["status"]) == 'success':  # 成功
            if not ret['transaction_id'] == "":  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['transaction_id'], data['code']))
                logging.info('notice_RED_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(code=data['status'], third_code=ret['transaction_id'], message=ret.get('msg'),status=ret['status'],data=ret))
            logging.info('notice_RED_Pay 订单-{code}-成功-返回成功'.format(code=data['code']))
            return True
        else:
            # 失败
            logging.error('notice_RED_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_RED_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_RED_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def lucky(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # lucky代付
    notify = "/df_notice/lucky"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['clientCode'] = mer_id
        data_post['chainName'] = 'BANK'
        data_post['coinUnit'] = 'INR'
        data_post['bankCardNum'] = data['payment_account']
        data_post['bankUserName'] = data['payment_name']
        data_post['ifsc'] = data['ifsc']
        data_post['bankName'] = data['payment_bank']
        data_post['amount'] = data['amount']
        data_post['clientNo'] = data['code']
        data_post['requestTimestamp'] = int(round(time.time() * 1000))
        data_post['callbackurl'] = host + notify
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key, "AGDF")
        data_post['sign'] = data_post['sign'].lower()

        logging.info('notice_LUCKY_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, timeout=(5,10), verify=False)
        logging.info('notice_LUCKY_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        if ret['success'] is True:
            logging.error('notice_LUCKY_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_LUCKY_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_LUCKY_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_LUCKY_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def apay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # apay代付
    notify = "/df_notice/apay"
    try:
        conf = get_config()
        notice_domain_api_list = rds.get('notice_domain_api_list')

        if not notice_domain_api_list:
            host = conf['ospay_api_host']
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['version'] = '1.6'
        data_post['cid'] = mer_id
        data_post['tradeNo'] = data['code']
        data_post['amount'] = int(decimal.Decimal(data['amount']) * 100)
        data_post['payType'] = '1'
        data_post['acctName'] = data['payment_name']
        data_post['acctNo'] = data['payment_account']
        data_post['bankCode'] = '301'
        data_post['ifscCode'] = data['ifsc']
        data_post['memo'] = 'JSON'
        data_post['notifyUrl'] = host + notify
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)
        data_post['sign'] = data_post['sign'].lower()
        # data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        logging.info('notice_APAY_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_APAY_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        if str(ret.get('retcode')) == '0' and str(ret.get('status')) == '2':
            if ret['rockTradeNo']:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['rockTradeNo'], data['code']))
                logging.info('notice_RED_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['status'], third_code=ret['rockTradeNo'], message=ret.get('message'), status=ret['status'], data=ret))
            logging.error('notice_APAY_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_APAY_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_APAY_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_APAY_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def globe(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # globe代付
    notify = "/df_notice/globe"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['merchantCode'] = mer_id
        data_post['merchantOrderId'] = data['code']
        data_post['serviceId'] = 'B001'
        data_post['applyAmount'] = str(data['amount'])
        data_post['applyUserName'] = data['payment_name']
        data_post['applyAccount'] = data['payment_account']
        data_post['callbackUrl'] = host + notify
        data_post['applyBankCode'] = 'IN0001'
        data_post['applyIfsc'] = data['ifsc']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)
        data_post['sign'] = data_post['sign'].lower()
        data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        logging.info('notice_Globe_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_Globe_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)

        if str(ret.get('code')) == '00':
            if ret['data'].get('orderId'):  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['data'].get('orderId'), data['code']))
                logging.info('notice_RED_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['status'], third_code=ret['data'].get('orderId'), message=ret.get('code'), status=ret.get('code'), data=ret))
            logging.error('notice_Globe_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_Globe_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_Globe_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_Globe_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def rupix(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # rupix代付
    notify = "/df_notice/rupix"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['appId'] = mer_id
        data_post['outTradeNo'] = data['code']
        data_post['ifscCode'] = data['ifsc']
        data_post['nonceStr'] = ''.join(random.choice(string.ascii_letters) for _ in range(10))
        data_post['accountNumber'] = data['payment_account']
        data_post['accountName'] = data['payment_name']
        data_post['amount'] = data['amount']
        data_post['asyncUrl'] = host + notify
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)
        # data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        logging.info('notice_Rupix_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_Rupix_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('code')) == '200':
            if ret['data'].get('outTradeNo'):  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret['data'].get('sn'), data['code']))
                logging.info('notice_Rupix_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=ret['data'].get('outTradeNo'), message=ret.get('msg'), status=ret.get('code'), data=ret))
            logging.info('notice_Rupix_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_Rupix_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_Rupix_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_Rupix_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def pay58pay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # pay58pay代付
    notify = "/df_notice/pay58pay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['mchId'] = mer_id
        data_post['productId'] = '3020'
        data_post['mchOrderNo'] = data['code']
        data_post['amount'] = int(decimal.Decimal(data['amount']) * 100)
        data_post['clientIp'] = '0.0.0.0'
        data_post['notifyUrl'] = host + notify
        data_post['userName'] = data['payment_name']
        data_post['cardNumber'] = data['payment_account']
        data_post['ifscCode'] = data['ifsc']
        data_post['bankName'] = ''

        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key, key_name='secretKey')
        data_post = json.dumps(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        logging.info('notice_pay58pay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_pay58pay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('retCode')) == 'SUCCESS':
            if ret.get('payOrderId'):  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret.get('payOrderId'), data['code']))
                logging.info('notice_pay58pay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=ret.get('payOrderId'), message=ret.get('retMsg'), status=ret.get('status'), data=ret))
            logging.info('notice_pay58pay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_pay58pay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_pay58pay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_Rupix_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def kuaiyin(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # kuaiyin代付
    notify = "/df_notice/kuaiyin"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['out_trade_no'] = data['code']
        data_post['bank_account'] = data['payment_name']
        data_post['card_no'] = data['payment_account']
        data_post['bank_name'] = '5157'
        data_post['bank_province'] = ''
        data_post['bank_city'] = ''
        data_post['sub_bank'] = data['ifsc']
        data_post['amount'] = data['amount']
        data_post['notify_url'] = host + notify
        data_post['currency'] = 'INR'
        data_post['send_ip'] = '0.0.0.0'
        data_post['attach'] = ''

        headers = {
            'sid': mer_id,
            'nonce': str(uuid.uuid4()),
            'timestamp': str(int(round(time.time() * 1000))),
            'url': '/payfor/trans',
        }

        # 排序header参数和body参数
        sorted_header = sorted(headers.items())
        header_text = ''.join(f"{k}{v}" for k, v in sorted_header)
        sorted_body = sorted(data_post.items())
        body_text = ''.join(f"{k}{v}" for k, v in sorted_body)

        sign_data = {
            'header_text': header_text,
            'body_text': body_text
        }
        headers['sign'] = SignatureAndVerification.md5_sign(sign_data, mer_key, key_name='KUAIYIN')
        logging.info('notice_kuaiyin_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_kuaiyin_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('code')) == '1000':
            if ret.get('trade_no'):  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (ret.get('trade_no'), data['code']))
                logging.info('notice_kuaiyin_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=ret.get('trade_no'), message=ret.get('msg'), status=ret.get('msg'), data=ret))
            logging.info('notice_kuaiyin_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_kuaiyin_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_kuaiyin_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_kuaiyin_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def wepay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    WePay 代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/wepay"
    notice_domain_api_list = rds.get('notice_domain_api_list')

    
    if not notice_domain_api_list:
        host = "https://ospay689.com/api"
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
        rs = len(notice_domain_api_list)
        rs = random.randint(0,rs-1)
        host = notice_domain_api_list[rs]

    back_url = host + notify  # 异步回调地址
    logging.info(f'back_url={back_url}')
    # 代付请求参数
    data_post = {
        "mch_id": mer_id,  # 商户代码
        "mch_transferId": data['code'],  # 商户转账订单号
        "transfer_amount": str(int(decimal.Decimal(data['amount']))),  # 代付金额（整数）
        "apply_date": time.strftime("%Y-%m-%d %H:%M:%S"),  # 申请时间
        "bank_code": "IDPT0001",  # 固定值
        "receive_name": data['payment_name'],  # 收款人姓名
        "receive_account": data['payment_account'],  # 收款银行账号
        "remark": data['ifsc'],  # IFSC 号码
        "sign_type": "MD5",  # 固定值
        "back_url": back_url,  # 回调地址
    }

    # 生成签名
    sign = generate_md5_signature(data_post, mer_key)
    data_post["sign"] = sign

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    try:
        logging.info(f'WePay Transfer 订单-{data["code"]}-发送地址 {pay_url}, 发送数据 {data_post}')
        logging.info(f'pay_url==={pay_url}')
        response = requests.post(pay_url, data=urlencode(data_post), headers=headers, timeout=(5, 10))
        
        logging.info(f'W1ePay Transfer 订单-{data["code"]}-返回结果 {response.text}')

        ret = json.loads(response.text)

        # logging.info('tradeResult=======', ret.get("tradeResult"))
        # logging.info('tradeNo=======', ret.get("tradeNo"))
        if str(ret.get("tradeResult")) == "0":
            # 订单提交成功，保存三方订单号
            if ret.get("tradeNo"):
                sql = "UPDATE orders_df SET otherpay_code=%s WHERE code=%s"
                cur.execute(sql, (ret.get("tradeNo"), data["code"]))
                logging.info(f'WePay Transfer 订单-{data["code"]}-成功, 三方订单号-{ret.get("tradeNo")}')
            return True
        else:
            logging.error(f'WePay Transfer 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'WePay Transfer 订单-{data["code"]}-超时异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'WePay Transfer 订单-{data["code"]}-连接异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'WePay Transfer 订单-{data["code"]}-异常: {e}')
        return False


def generate_md5_signature(params, private_key):
    """
    生成 WePay 签名
    :param params: 需要签名的参数字典 (不包含 sign 和 sign_type)
    :param private_key: 商户私钥
    :return: MD5 签名 (小写)
    """
    # 过滤掉 sign 和 sign_type，并移除值为空的字段
    filtered_params = {k: v for k, v in params.items() if k not in ["sign", "sign_type"] and v}

    # 按照 **ASCII 码** 升序排序
    sorted_params = sorted(filtered_params.items())

    # 按照 `k=v&k=v` 格式拼接字符串
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

    # 在字符串后面拼接商户私钥 `&key=x`
    query_string += f"&key={private_key}"

    # print("请求参数签名串：", query_string)  # 打印待签名字符串

    # 进行 MD5 加密，并转换为小写
    md5_hash = hashlib.md5(query_string.encode('utf-8')).hexdigest().lower()

    return md5_hash

def lemonpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    LemonPay 代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/lemonpay"
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = "https://ospay689.com/api"
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify  # 异步回调地址
    logging.info(f'back_url={back_url}')

    # 代付请求参数
    data_post = {
        "uid": mer_id,  # 商户 UID
        "merchant_num": mer_id,  # 商户号
        "order": data['code'],  # 订单号
        "currency": "INR",  # 货币（固定值）
        "coin": str(int(decimal.Decimal(data['amount']) * 100)),  # 金额（单位：分）
        "target_bank": data['payment_account'],  # 收款银行账号
        "bank_name": data['payment_bank'] or 'SBI',  # 银行名称
        "target_bank_user": data['payment_name'],  # 持卡人姓名
        "extend": data['ifsc'],  # IFSC 码
        "order_date": time.strftime("%Y-%m-%d %H:%M:%S"),  # 订单时间
        "notifyurl": back_url  # 异步回调地址
    }
    
    # 生成签名 
    sign = generate_lemon_signature(data_post, mer_key)
    data_post["sign"] = sign

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        logging.info(f'LemonPay Transfer 订单-{data["code"]}-发送地址 {pay_url}, 发送数据 {data_post}')
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 10))
        
        logging.info(f'LemonPay Transfer 订单-{data["code"]}-返回结果 {response.text}')
        ret = json.loads(response.text)
        logging.info(f"LemonPay Transfer 订单-{data["code"]}-返回结果: {ret}")
        # print(f"LemonPay Transfer 订单-{data["code"]}--发送地址 {pay_url}, 发送数据 {data_post}-返回结果: {ret}")
        if str(ret.get("code")) == "1":
            # 订单提交成功，保存三方订单号
            if ret.get("order"):
                sql = "UPDATE orders_df SET otherpay_code=%s WHERE code=%s"
                cur.execute(sql, (ret.get("order"), data["code"]))
                logging.info(f'LemonPay Transfer 订单-{data["code"]}-成功, 三方订单号-{ret.get("order")}')
            return True
        else:
            logging.error(f'LemonPay Transfer 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'LemonPay Transfer 订单-{data["code"]}-超时异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'LemonPay Transfer 订单-{data["code"]}-连接异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'LemonPay Transfer 订单-{data["code"]}-异常: {e}')
        return False


def generate_lemon_signature(params, private_key):
    """
    生成 LemonPay 签名
    :param params: 需要签名的参数字典（不包含 sign）
    :param private_key: 商户密钥
    :return: MD5 签名（大写）
    """
    # 过滤掉 sign，并移除值为空的字段
    filtered_params = {k: v for k, v in params.items() if k != "sign" and v}

    # 按 **ASCII 码** 升序排序
    sorted_params = sorted(filtered_params.items())

    # 按 `k=v&k=v` 格式拼接字符串
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

    # 在字符串后面拼接商户密钥 `&key=x`
    query_string += f"&key={private_key}"

    # 进行 MD5 加密，并转换为大写
    md5_hash = hashlib.md5(query_string.encode('utf-8')).hexdigest().upper()

    return md5_hash


def pay777pay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # pay777pay代付
    notify = "/df_notice/pay777pay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['app_id'] = mer_id
        data_post['merchant_order_id'] = data['code']
        data_post['amount'] = data['amount']
        data_post['customer_name'] = data['payment_name']
        data_post['payout_mode'] = 'INDIA_IMPS'
        data_post['customer_account_type'] = data['ifsc']
        data_post['customer_account_no'] = data['payment_account']
        data_post['notify_url'] = host + notify

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)
        data_post['sign'] = data_post['sign'].lower()
        logging.info('notice_pay777pay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_pay777pay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('code')) == '200':
            otherpay_code = ret.get('data', {}).get('system_order_id')
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_pay777pay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('message'), status=ret.get('code'), data=ret))
            logging.info('notice_pay777pay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_pay777pay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_pay777pay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_pay777pay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def swiftpay(cur, rds, logging, data, mer_id, mer_key, mer_key2, mer_key3, pay_url):
    # swiftpay代付
    notify = "/df_notice/swiftpay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['merchantNo'] = mer_id
        data_post['orderId'] = data['code']
        data_post['payment'] = int(data['amount'])
        data_post['userName'] = data['payment_name']
        data_post['userAccount'] = data['payment_account']
        data_post['userMobile'] = '1234567890'
        data_post['userIFSC'] = data['ifsc']
        data_post['callback'] = host + notify
        data_post['sign'] = SignatureAndVerification.sha1_sign(data_post, mer_key3)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/json'
        }
        data_post = json.dumps(data_post)
        logging.info('notice_swiftpay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_swiftpay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('errNo')) == '0':
            otherpay_code = ret.get('data', {}).get('payoutNo')
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_swiftpay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('errStr'), status=ret.get('data', {}).get('status'), data=ret))
            logging.info('notice_swiftpay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_swiftpay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_swiftpay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_swiftpay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def lemonpay2(cur, rds, logging, data, mer_id, mer_key, mer_key2, mer_key3, pay_url):
    # lemonpay2代付
    notify = "/df_notice/lemonpay2"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['mer_no'] = mer_id
        data_post['order_no'] = data['code']
        data_post['amount'] = data['amount']
        data_post['currency'] = 'INR'
        data_post['bank_code'] = data['ifsc']
        data_post['name'] = data['payment_name']
        data_post['account'] = data['payment_account']
        data_post['phone'] = '1234567890'
        data_post['email'] = "vanhimus@gmail.com"
        data_post['notify_url'] = host + notify
        data_post['sign'] = SignatureAndVerification.sha256_sign(data_post, mer_key3, key_type='PKCS#8', is_url=False)
        print(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/json'
        }
        data_post = json.dumps(data_post)
        logging.info('notice_lemonpay2_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_lemonpay2_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('code')) == '200':
            otherpay_code = ret.get('data', {}).get('sys_no')
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_lemonpay2_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('errStr'), status=ret.get('data', {}).get('status'), data=ret))
            logging.info('notice_lemonpay2_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_lemonpay2_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_lemonpay2_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_lemonpay2_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def quickpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    QuickPay 代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/quickpay"
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = "https://ospay689.com/api"
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify  # 异步回调地址
    logging.info(f'back_url={back_url}')

    data_post = {
    "merchantNo": str(mer_id),
    "orderId": str(data['code']),
    "payment": str(int(decimal.Decimal(data['amount']))),
    "userName": str(data['payment_name']),
    "userAccount": str(data['payment_account']),
    "userMobile": '917893305473',
    "userIFSC": str(data['ifsc']),
    "callback": str(back_url),
    }
    
    # 生成签名 (使用 RSA + SHA1 签名)
    # print(data_post, mer_key)
    sign = SignatureAndVerification.rsa_sha1_sign(data_post, mer_key)
    data_post["sign"] = sign
    headers = {
        "Content-Type": "application/json"
    }
    data_post = json.dumps(data_post)  # 转换为 JSON 字符串

    try:
        logging.info(f'QuickPay Transfer 订单-{data["code"]}-发送地址 {pay_url}, 发送数据 {data_post}')
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 10))
        
        logging.info(f'QuickPay Transfer 订单-{data["code"]}-返回结果 {response.text}')
        ret = json.loads(response.text)
        logging.info(f"QuickPay Transfer 订单-{data['code']}-返回结果: {ret}")
        
        if str(ret.get("errNo")) == "0":
            # 订单提交成功，保存三方订单号
            otherpay_code = ret["data"]["payoutNo"]
            logging.info(f"payoutNo: {otherpay_code}")
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "UPDATE orders_df SET otherpay_code=%s WHERE code=%s"
                cur.execute(sql, (otherpay_code, data["code"]))
                logging.info(f'QuickPay Transfer 订单-{data["code"]}-成功, 三方订单号-{otherpay_code}')
            return True
        else:
            logging.error(f'QuickPay Transfer 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'QuickPay Transfer 订单-{data["code"]}-超时异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'QuickPay Transfer 订单-{data["code"]}-连接异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'QuickPay Transfer 订单-{data["code"]}-异常: {e}')
        return False


def snakepay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    # snakepay代付
    notify = "/df_notice/snakepay"
    try:
        notice_domain_api_list = rds.get('notice_domain_api_list')
        if not notice_domain_api_list:
            # host = self.request.protocol + '://' + self.request.host
            host = "https://ospay689.com/api"
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0,rs-1)
            host = notice_domain_api_list[rs]

        data_post = dict()
        data_post['merchantNo'] = mer_id
        data_post['orderNo'] = data['code']
        data_post['amount'] = data['amount']
        data_post['notifyUrl'] = host + notify
        data_post['mode'] = 'IMPS'
        data_post['accountNo'] = data['payment_account']
        data_post['accountName'] = data['payment_name']
        data_post['ifsc'] = data['ifsc']
        data_post['sign'] = SignatureAndVerification.hmac_sha256_sign(data_post, mer_key)
        # print(data_post)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/json'
        }
        data_post = json.dumps(data_post)
        logging.info('notice_snakepay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_snakepay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('code')) == '200':
            otherpay_code = ret.get('data', {}).get('platformOrderNo')
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_snakepay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('msg'), status=ret.get('code'), data=ret))
            logging.info('notice_snakepay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_snakepay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_snakepay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_snakepay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def hkpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    HKPay 代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/hkpay"
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = "https://ospay689.com/api"
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify  # 异步回调地址
    # back_url = 'https://30f9-47-238-21-150.ngrok-free.app/hkpay'
    logging.info(f'back_url={back_url}')

    # 组织请求参数
    data_post = {
        "merchantid": str(mer_id),
        "passage_code": "200001",
        "merchant_orderno": str(data['code']),
        "currency": "INR",
        "amount": f"{decimal.Decimal(data['amount']):.2f}",  # 保留两位小数
        "pay_recipients_name": str(data['payment_name']),
        "pay_bankname": str(data['payment_bank']),
        "pay_bank_account": str(data['payment_account']),
        "pay_ifsc": str(data['ifsc']),
        "notify_url": str(back_url),
    }

    # **1. 生成签名**
    sign = generate_md5_signature(data_post, mer_key)
    data_post["sign"] = sign  # 加入签名

    # **2. 发送请求**
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        logging.info(f'HKPay Transfer 订单-{data["code"]}-发送地址 {pay_url}, 发送数据 {data_post}')
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 10))

        logging.info(f'HKPay Transfer 订单-{data["code"]}-返回结果 {response.text}')
        ret = response.json()
        
        if str(ret.get("code")) == "200":
            # 订单提交成功，保存三方订单号
            otherpay_code = ret["data"]["orderno"]
            logging.info(f"HKPay 订单号: {otherpay_code}")
            if otherpay_code:
                sql = "UPDATE orders_df SET otherpay_code=%s WHERE code=%s"
                cur.execute(sql, (otherpay_code, data["code"]))
                logging.info(f'HKPay Transfer 订单-{data["code"]}-成功, 三方订单号-{otherpay_code}')
            return True
        else:
            logging.error(f'HKPay Transfer 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'HKPay Transfer 订单-{data["code"]}-超时异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'HKPay Transfer 订单-{data["code"]}-连接异常, 发送地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'HKPay Transfer 订单-{data["code"]}-异常: {e}')
        return False


def generate_md5_signature(params, md5_key):
    """
    生成 MD5 签名
    - 按 ASCII 排序
    - 拼接成 key=value&key=value 形式
    - 追加 &key=md5_key
    - 计算 MD5 并转换为小写
    """
    sorted_items = sorted(params.items())  # 按 key 进行 ASCII 排序
    sign_string = "&".join(f"{k}={v.strip()}" for k, v in sorted_items if v)  # 去除空值
    sign_string += f"&key={md5_key}"  # 追加密钥

    md5_hash = hashlib.md5(sign_string.encode('utf-8')).hexdigest()  # 计算 MD5
    return md5_hash.lower()  # 转小写


def skpay(cur, rds, logging, data, mer_id, accesskey, pay_url, secretkey):
    # skpay代付
    notify = "/df_notice/skpay"
    try:
        conf = get_config()
        notice_domain_api_list = rds.get('notice_domain_api_list')

        if not notice_domain_api_list:
            host = conf['ospay_api_host']
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['merchantOrderNo'] = data['code']
        data_post['beneficiary'] = data['payment_name']
        data_post['bankName'] = data['payment_bank']
        data_post['bankAccount'] = data['payment_account']
        data_post['ifsc'] = data['ifsc']
        data_post['currency'] = 'inr' # 币种卢比[or usdt]
        data_post['amount'] = data['amount']
        data_post['channelCode'] = "ch70471" # 通道代码 UPI
        data_post['notifyUrl'] = host + notify

        # 提取 path，不包含域名及参数，只保留 /mcapi/quota
        url_path = urlparse(pay_url).path
        signature_info = SignatureAndVerification.generate_signature_skpay("POST", url_path, accesskey, secretkey)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/json',
            "accessKey": accesskey,
            "timestamp": signature_info["timestamp"],
            "nonce": signature_info["nonce"],
            "sign": signature_info["sign"]
            
        }
        data_post = json.dumps(data_post)
        logging.info('notice_skpay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_skpay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('code')) == '200000':
            otherpay_code = ret.get('data', {}).get('orderNo') # 三方订单号
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_skpay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('message'), status=ret.get('code'), data=ret))
            logging.info('notice_skpay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_skpay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_skpay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_skpay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def catspay(cur, rds, logging, data, mer_id, secretkey, pay_url):
    # catspay代付
    notify = "/df_notice/catspay"
    try:
        conf = get_config()
        notice_domain_api_list = rds.get('notice_domain_api_list')

        if not notice_domain_api_list:
            host = conf['ospay_api_host']
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]
        # 查询订单确保回调安全
        data_post = dict()
        data_post['merchant_id'] = mer_id
        data_post['merchant_orderid'] = data['code']
        data_post['currency'] = 'INR'
        data_post['money'] = data['amount']
        data_post['bankusername'] = data['payment_name']
        data_post['bankname'] = data['payment_bank']
        data_post['bankcode'] = data['payment_account']
        data_post['yuliu1'] = data['ifsc']
        data_post['notifyurl'] = host + notify
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, secretkey, 'catspay').lower()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/x-www-form-urlencoded',

        }
        logging.info('notice_catspay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_catspay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if str(ret.get('status')) == '1':
            otherpay_code = ret.get('data', {}).get('orderid') # 三方订单号
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_catspay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('message'), status=ret.get('code'), data=ret))
            logging.info('notice_catspay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_catspay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_catspay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_catspay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def lemonpay3(cur, rds, logging, data, mer_id, secretkey, pay_url):
    # lemonpay3代付
    notify = "/df_notice/lemonpay3"
    try:
        conf = get_config()
        notice_domain_api_list = rds.get('notice_domain_api_list')

        if not notice_domain_api_list:
            host = conf['ospay_api_host']
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]
        # 下单参数
        data_post = dict()
        data_post['mchId'] = mer_id
        data_post['productId'] = 8040
        data_post['mchOrderNo'] = data['code']
        data_post['amount'] = int(decimal.Decimal(data['amount']) * 100)
        data_post['currency'] = 'INR'
        data_post['collectionType'] = 'bank'
        data_post['bankName'] = data['payment_bank']
        data_post['accountName'] = data['payment_name']
        data_post['accountNo'] = data['payment_account']
        data_post['bankNumber'] = data['ifsc']
        data_post['remark'] = 'Pay'
        data_post['notifyUrl'] = host + notify
        data_post['reqTime'] = time.strftime("%Y%m%d%H%M%S")
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, secretkey)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/x-www-form-urlencoded',

        }
        logging.info('notice_lemonpay3_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_lemonpay3_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if ret.get('retCode') == 'SUCCESS':
            otherpay_code = ret.get('agentpayOrderId') # 三方订单号
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_lemonpay3_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('retMsg'), status=ret.get('status'), data=ret))
            logging.info('notice_lemonpay3_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_lemonpay3_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_lemonpay3_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_lemonpay3_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False


def pay188pay(cur, rds, logging, data, mer_id, secretkey, pay_url):
    # 188pay代付
    notify = "/df_notice/188pay"
    try:
        conf = get_config()
        notice_domain_api_list = rds.get('notice_domain_api_list')

        if not notice_domain_api_list:
            host = conf['ospay_api_host']
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]
        # 下单参数
        data_post = dict()
        data_post['merchno'] = mer_id
        data_post['orderId'] = data['code']
        data_post['amount'] = data['amount']
        data_post['tradeType'] = '1'
        data_post['account'] = data['payment_name']
        data_post['cardNo'] = data['payment_account']
        data_post['bankName'] = data['ifsc'][:4]
        data_post['depositBank'] = data['ifsc']
        data_post['asyncUrl'] = host + notify
        data_post['timestamp'] = time.strftime("%Y%m%d%H%M%S")
        data_post['cashType'] = 4
        data_post['requestCurrency'] = 4
        data_post['apiVersion'] = 2
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, secretkey, key_name='secretKey').lower()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/x-www-form-urlencoded',

        }
        logging.info('notice_188pay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_188pay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        ret = ret.get('responseContent', {})
        if str(ret.get('code')) == '0':
            otherpay_code = ret.get('orderNo')  # 三方订单号
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_188pay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('msg'), status=ret.get('status'), data=ret))
            logging.info('notice_188pay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error('notice_188pay_Pay 订单-{code}-失败'.format(code=data['code']))
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_188pay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_188pay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def tatapay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    Tatapay 代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/tatapay"
    conf = get_config()
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = conf['ospay_api_host']
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify
    logging.info(f'[tatapay] 回调地址 back_url={back_url}')

    # 组织请求参数
    data_post = {
        "merchNo": str(mer_id),
        "orderNo": str(data["code"]),
        "amount": f"{decimal.Decimal(data['amount']):.2f}",
        "currency": "INR",
        "acctName": str(data["payment_name"]),  # 格式: first@last
        "acctCode": str(data["ifsc"]),     # GCASH / PAYMAYA / IFSC...
        "acctNo": str(data["payment_account"]),
        "mobile": "18602667777",
    }

    # 生成签名
    sign = generate_tatapay_signature(data_post, mer_key)
    data_post["sign"] = sign
    try:
        headers = {
            "Content-Type": "application/json"
        }
        logging.info(f'[tatapay] Transfer 订单-{data["code"]}-发送地址 {pay_url}, 发送数据 {data_post}')
        response = requests.post(pay_url, json=data_post, headers=headers, timeout=(5, 10))

        logging.info(f'[tatapay] Transfer 订单-{data["code"]}-返回结果 {response.text}')
        ret = response.json()
        logging.info(f'[tatapay] Transfer 订单-code-返回结果 {ret.get("code")}')
        if str(ret.get("code")) == "0":
            return True
        else:
            logging.error(f'[tatapay] Transfer 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'[tatapay] Transfer 订单-{data["code"]}-超时异常, 地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'[tatapay] Transfer 订单-{data["code"]}-连接异常, 地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'[tatapay] Transfer 订单-{data["code"]}-其他异常: {e}')
        return False
def generate_tatapay_signature(params, md5_key):
    """
    生成 tatapay 签名
    - 所有参数 key=value
    - 按 key 字典序排序
    - 用 & 拼接
    - 末尾拼接 md5_key（无符号）
    - 生成 MD5 签名
    """
    sorted_items = sorted(params.items())
    sign_str = "&".join(f"{k}={v}" for k, v in sorted_items)
    sign_str += md5_key  # 注意：无 & 符号
    md5_hash = hashlib.md5(sign_str.encode("utf-8")).hexdigest()
    return md5_hash.lower()

def ospay(cur, rds, logging, data, mer_id, secretkey, pay_url):
    # ospay代付
    notify = "/df_notice/ospay"
    try:
        conf = get_config()
        notice_domain_api_list = rds.get('notice_domain_api_list')

        if not notice_domain_api_list:
            host = conf['ospay_api_host']
        else:
            notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]
        # 下单参数
        data_post = dict()
        data_post['mer_id'] = mer_id
        data_post['order_id'] = data['code']
        data_post['amount'] = data['amount']
        data_post['notify'] = host + notify
        data_post['gateway'] = '1' # 1 银行卡， 2 UPI
        data_post['user'] = data['payment_name']
        data_post['account'] = data['payment_account']
        data_post['bank'] = data['payment_bank']
        data_post['bank_code'] = data['ifsc']
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, secretkey)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        logging.info('notice_ospay_Pay 订单-{code}-发送地址{url},发送{data_post}'.format(code=data['code'], url=pay_url, data_post=data_post))
        r = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10), verify=False)
        logging.info('notice_ospay_Pay 代付订单-{code}-发送地址{url},发送{data_post},结果{ret}'.format(code=data['code'], url=pay_url, data_post=data_post, ret=r.text))
        ret = json.loads(r.text)
        if ret.get('code') == 0:
            otherpay_code = ret.get('order_code')  # 三方订单号
            if otherpay_code:  # 如果成功有三方的订单号，进行保存
                sql = "update orders_df set otherpay_code=%s where code=%s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info('notice_ospay_Pay 订单-{code}-{third_code} 成功-{message}-{status}-{data}'.format(
                    code=data['code'], third_code=otherpay_code, message=ret.get('message'), status=ret.get('code'), data=ret))
            logging.info('notice_ospay_Pay 订单-{code}-成功'.format(code=data['code']))
            return True
        else:
            logging.error(f'notice_ospay_Pay 订单-{data['code']}-失败, {ret.get('message')}')
            return False
    except requests.exceptions.Timeout as e:
        logging.exception('notice_ospay_Pay-代付订单-{code}-超时异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception('notice_ospay_Pay-代付订单-{code}-ConnectionError异常,先生成本平台订单：发送地址{url},结果{e}'.format(code=data['code'], url=pay_url, e=e))
        return True
    except Exception as e:
        logging.exception(e)
        return False

def vibrapay(cur, rds, logging, data, mer_id, mer_key, pay_url, mer_key2):
    """
    vibrapay代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/vibrapay"
    conf = get_config()
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = conf['ospay_api_host']
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify
    logging.info(f'[vibrapay] 回调地址 back_url={back_url}')

    df_params = {
        "gateway": "payout",
        "merchant_order_num": str(data["code"]),
        "uid": str(data["code"]),
        "amount": f"{decimal.Decimal(data['amount']):.2f}",
        "bank_code": "AXISINBB",
        "ifsc_code": data["ifsc"],
        "card_number": data["payment_account"],
        "card_holder": data["payment_name"],
        "province_code": "10000",
        "city_code": "10000",
        "area_code": "10000",
        "merchant_order_time": int(time.time()),
        "user_ip": "127.0.0.1",
        "callback_url": back_url,
    }

    sorted_df_params = dict(sorted(df_params.items()))
    encrypted_df_params = SignatureAndVerification.aes_256_cbc_encrypt(mer_key, mer_key2, json.dumps(sorted_df_params))
    data_post = {
        "merchant_slug": mer_id,
        "data": encrypted_df_params
    }
    try:
        headers = {
            "Content-Type": "application/json"
        }
        logging.info(f'[vibrapay] withdraw 订单-{data["code"]}-发送地址 {pay_url}, 订单参数 {df_params} 发送数据 {data_post}')
        response = requests.post(pay_url, json=data_post, headers=headers, timeout=(5, 10))
        logging.info(f'[vibrapay] withdraw 订单-{data["code"]}-返回结果 {response.text}')
        ret = response.json()
        logging.info(f'[vibrapay] withdraw 订单-code-返回结果 {ret.get("code")}')
        if str(ret.get("code")) == '0':
            encrypted_order = ret.get("order")
            order = SignatureAndVerification.aes_256_cbc_decrypt(mer_key, mer_key2, encrypted_order)
            logging.info(f'[vibrapay] withdraw 订单-{data["code"]}-解密的订单信息 {order}')
            return True
        else:
            logging.error(f'[vibrapay] withdraw 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False
    
    except requests.exceptions.Timeout as e:
        logging.exception(f'[vibrapay] withdraw 订单-{data["code"]}-超时异常, 地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'[vibrapay] withdraw 订单-{data["code"]}-连接异常, 地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'[vibrapay] withdraw 订单-{data["code"]}-其他异常: {e}')
        return False


def qqpay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    qqpay代付请求
    """
    # 配置异步通知回调地址
    notify = "/df_notice/qqpay"
    conf = get_config()
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = conf['ospay_api_host']
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify
    logging.info(f'[qqpay] 回调地址 back_url={back_url}')

    df_params = {
        "merchant_id": mer_id,
        "mer_order_num": str(data["code"]),
        "price": f"{decimal.Decimal(data['amount']):.2f}",
        "account_name": data["payment_name"],
        "account_num": data["payment_account"],
        "account_bank": data["payment_bank"],
        "remark": data["ifsc"],
        "notify_url": back_url,
        "timestamp": str(int(time.time()))
    }
    df_params['sign'] = SignatureAndVerification.hmac_sha256_sign3(df_params, mer_key)

    try:
        headers = {
            "Content-Type": "application/json"
        }
        df_params_json = json.dumps(df_params)
        logging.info(f'[qqpay] withdraw 订单-{data["code"]}-发送地址 {pay_url}, 订单参数 {df_params} 发送数据 {df_params_json}')
        response = requests.post(pay_url, data=df_params_json, headers=headers, timeout=(5, 10))
        logging.info(f'[qqpay] withdraw 订单-{data["code"]}-返回结果 {response.text}')
        ret = response.json()
        logging.info(f'[qqpay] withdraw 订单-code-返回结果 {ret}')
        if str(ret.get("code")) == '200':
            transfer_id = ret.get('data')['order_num']
            logging.info(f"[openmoney] 代付成功，转账 ID: {transfer_id}")
            # 保存三方订单号
            if transfer_id:
                sql = "UPDATE orders_df SET otherpay_code = %s WHERE code = %s"
                cur.execute(sql, (transfer_id, data['code']))
                logging.info(
                    f"[openmoney] 保存订单号成功，订单编号: {data['code']}，三方转账号: {transfer_id}"
                )
            logging.info(f"[openmoney] notice_openmoney_Pay 订单-{data['code']}-成功")
            return True
        else:
            logging.error(f'[qqpay] withdraw 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'[qqpay] withdraw 订单-{data["code"]}-超时异常, 地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'[qqpay] withdraw 订单-{data["code"]}-连接异常, 地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'[qqpay] withdraw 订单-{data["code"]}-其他异常: {e}')
        return False
    

def marspay(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    MarsPay代付请求
    """
    # ------------------ 查询余额 (Check Balance) ------------------
    # 余额查询接口
    balance_endpoint = "https://mars-pay.in/api/telecom/v1/check-balance"
    balance_params = {"api_token": mer_key}

    try:
        balance_response = requests.get(balance_endpoint, params=balance_params, timeout=(5, 10))
        balance_response.raise_for_status()
        # balance_data = balance_response.json()
        balance_data = json.loads(balance_response.text)

        logging.info(f'[marspay] 代付订单-{data["code"]}-查询余额-发送地址{balance_endpoint}, 结果{balance_response.text}')

        if balance_data.get("status") == "success":
            balance = balance_data.get("balance", {}).get('normal_balance', '0')
        else:
            logging.info(f'[marspay] 代付订单-{data["code"]}-余额查询失败: {balance_data.get("message", "未知错误")}')
            return False

        # 校验余额是否充足
        cleaned_balance_str = balance.replace(",", "")
        payout_amount = decimal.Decimal(str(data['amount']))
        current_balance = decimal.Decimal(cleaned_balance_str)
        logging.info(f'[marspay] 代付订单-{data["code"]}-金额校验：代付金额={payout_amount}, 账户余额={current_balance}')

        if payout_amount > current_balance:
            logging.info(f'[marspay] 代付订单-{data["code"]}-失败, 余额不足, 当前余额: {current_balance}, 需付: {payout_amount}')
            return False
        
    except requests.exceptions.RequestException as e:
        logging.exception(f'[marspay] 代付订单-{data["code"]}-余额查询失败: {e}')
        return False
    except Exception as e:
        logging.exception(f'[marspay] 代付订单-{data["code"]}-余额查询异常: {e}')
        return False

    # ------------------ 发起代付请求 (Payout Request) ------------------
    notify = "/df_notice/marspay"
    
    conf = get_config()
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = conf['ospay_api_host']
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]

    back_url = host + notify
    logging.info(f'[marspay] 回调地址 back_url={back_url}')

    # 构建代付请求参数
    df_params = {
        "api_token": mer_key,
        "mobile_number": '9' + ''.join(random.choices(string.digits, k=9)),
        "email": f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}@gmail.com",
        "beneficiary_name": data["payment_name"],
        "ifsc_code": data["ifsc"],
        "account_number": data["payment_account"],
        "amount": str(int(payout_amount)),
        "channel_id": "2",
        "client_id": str(data["code"]),
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        logging.info(f'[marspay] 代付订单-{data["code"]}-发送地址{pay_url}, 发送{df_params}')
        r = requests.post(pay_url, data=df_params, headers=headers, timeout=(5, 10))
        logging.info(f'marspay 代付订单-{data["code"]}-发送地址{pay_url}, 发送{df_params}, 结果{r.text}')

        ret = json.loads(r.text)
        
        # 成功判断
        if ret.get("status") == "success" or ret.get("status") == "pending":
            message = ret.get("message", "")
            utr = ret.get("utr", "")
            payid = ret.get("payid", "")
            
            sql = "UPDATE orders_df SET otherpay_code = %s WHERE code = %s"
            cur.execute(sql, (payid, data['code']))
            logging.info(f'marspay 订单-{data["code"]}-成功-返回成功: message={message}, utr={utr}, payid={payid}')
            return True
        else:
            # 失败判断
            logging.error(f'marspay 订单-{data["code"]}-失败: 结果{r.text}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'marspay-代付订单-{data["code"]}-超时异常, 先生成本平台订单: 发送地址{pay_url}, 错误{e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'marspay-代付订单-{data["code"]}-连接异常, 先生成本平台订单: 发送地址{pay_url}, 错误{e}')
        return True
    except Exception as e:
        logging.exception(e)
        return False

# Gamepayer支付
def Gamepayer(cur, rds, logging, data, mer_id, mer_key, pay_url):
    """
    Gamepayer 代付请求
    """
    pay_name = "gamepayer"
    notify = "/df_notice/gamepayer"
    conf = get_config()
    notice_domain_api_list = rds.get('notice_domain_api_list')

    if not notice_domain_api_list:
        host = conf['ospay_api_host']
    else:
        notice_domain_api_list = notice_domain_api_list.decode().strip().split(',')
        notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
        rs = len(notice_domain_api_list)
        rs = random.randint(0, rs - 1)
        host = notice_domain_api_list[rs]
    notifyurl = host + notify
    logging.info(f'[{pay_name}] 回调地址 notifyurl={notifyurl}')
    df_params = {
        "merchant_id": mer_id,  # 商户id
        "merchant_orderid": str(data["code"]),  # 商户订单号
        "currency": "PKR",
        "bankcode": data["payment_account"],  # 收款账号
        "bankusername": data["payment_name"],  # 收款⼈姓名
        "bankname": data["payment_bank"],  # 收款⼈银行
        "money": decimal.Decimal(data['amount']),  # 金额
        "notifyurl": notifyurl
    }
    df_params['sign'] = SignatureAndVerification.md5_sign(df_params, mer_key, "catspay").lower()

    try:
        headers = { "Content-Type": "application/x-www-form-urlencoded" }
        # df_params_json = json.dumps(df_params)
        logging.info(f'[{pay_name}] withdraw 订单-{data["code"]}-发送地址 {pay_url}, 发送数据 {json.dumps(df_params)}')
        response = requests.post(pay_url, data=df_params, headers=headers, timeout=(5, 10))
        logging.info(f'[{pay_name}] withdraw 订单-{data["code"]}-返回结果 {response.text}')
        ret = response.json()
        if str(ret.get("status")) == '1':
            res = ret.get('data', {})
            otherpay_code  = res.get('orderid', None)
            logging.info(f"[{pay_name}] 代付成功，转账 ID: {otherpay_code}")
            # 保存三方订单号
            if otherpay_code:
                sql = "UPDATE orders_df SET otherpay_code = %s WHERE code = %s"
                cur.execute(sql, (otherpay_code, data['code']))
                logging.info(f"[{pay_name}] 保存订单号成功，订单编号: {data['code']}，三方转账单号: {otherpay_code}")
            logging.info(f"[{pay_name}] notice_openmoney_Pay 订单-{data['code']}-成功")
            return True
        else:
            logging.error(f'[{pay_name}] withdraw 订单-{data["code"]}-失败, 返回信息: {ret}')
            return False

    except requests.exceptions.Timeout as e:
        logging.exception(f'[{pay_name}] withdraw 订单-{data["code"]}-超时异常, 地址 {pay_url}, 错误: {e}')
        return True
    except requests.exceptions.ConnectionError as e:
        logging.exception(f'[{pay_name}] withdraw 订单-{data["code"]}-连接异常, 地址 {pay_url}, 错误: {e}')
        return True
    except Exception as e:
        logging.exception(f'[{pay_name}] withdraw 订单-{data["code"]}-其他异常: {e}')
        return False
