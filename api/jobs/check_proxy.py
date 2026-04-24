import os
from datetime import datetime
import json
import random
import time
import traceback
import urllib
import requests
import redis
from config import get_config
import logging
from logging.handlers import TimedRotatingFileHandler
import psutil

# 检测所有的socks5代理ip
LOG_FILE = "check_proxy.log"
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fh = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15)
datefmt = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s %(message)s '
formatter = logging.Formatter(format_str, datefmt)
fh.setFormatter(formatter)
logger.addHandler(fh)
conf = get_config()

IF_get_new_proxies = False # 是否拉取新的代理

IP_LOWER = 4 # 代理ip低于多少个就告警

RETRY_TIMES = 5  # 重新尝试的次数

NOTIFY_TIME = 60 * 30 # 30分钟通知一次

IP_AT_LEAST = 8 # 默认低于多少就开始拉取新的代理ip

IP_GET_AT_ONE_TIME = 20 # 一次性获取ip的数量

# IPRoyal API配置
API_KEY = "73bd4709420ea3a6296539befec147a78f7868028f6c757c5c4bff595711"
API_BASE_URL = "https://apid.iproyal.com/v1/reseller"
PRODUCT_ID = 3  # 印度数据中心

# 用于检查代理的URL
check_urls = {
    'indian_socks_ip_jio': {
        'url':'https://jiopay.jpb.jio.com/papigateway/getSession/v2',
        'headers':{
            'User-Agent': 'okhttp/4.12.0',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'appVersion': '4085', # 需改动
            'app_language': 'en_US',
            'Content-Type': 'application/json; charset=UTF-8',
            # 'Cache-Control': 'no-cache',
            # 'Pragma': 'no-cache',
            'appChannel': 'jio-finance'
        },
        "data":{
            "data": f"{random.random()}|7781537675402928", # 需改动
            "versionNo": '4085',  # 需改动
            "platform": "ANDROID",
            "appChannel": "jio-finance"
        },
        'method': 'post',
        'status_code': 200,
    },
    'indian_socks_ip_phonepe': {
        'url': 'https://apicp1.phonepe.com/apis/users/v4/auth',
        'headers': {
            'Connection': 'Keep-Alive',
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'okhttp/4.12.0',
            'X-APP-ID': 'fdab17054b934ee28271230cb743d3a7',
            'X-CHECKMATE-CLIENT-ID': 'ANDROID',
            'X-CHECKMATE-KEY-VERSION': '3',
            'X-DG-CA': '2',
            'X-DG-G': '75725a59565656565947644869666471706b62775670784e7052716379625700',
            'Accept-Encoding': 'gzip',
            'X-Device-Fingerprint': '0000000684ih8hL3/Z3krw1vRzTRAWenjlNHCmDhgLMx4KHKn9nG76vA7rXqO/MN7cVGOiLml6rXLSZpnHluvgnOXghxRCoUb8RNJILmAefGtgLtq2TqPDYu8upVFYPUv+DD2eV2ksH2bx3GpmIc0vQ4+8t/ZNkWfliqQXciHXh8ITI9FmZZsbYU+59WLoGMCbruhGEghkJ89HIbE4+aKFcmNNEaicPNeWqjHASZmWRW9HsMpJjKQ8uXiyLxe2FbVZSbv9caswE9WeMdTLdnQPzWZfDMASJ/gCqBSnUl/4sE55m5tgm7BCZbd2d6R6G5/2j7k9zb9byUqWBf5GfFrlwvsgGPaLReJ70/mvArjs4Jts/SzQxpsEc3YlU32D3KFjBF7cXwK0V+g/L1AORe8vuOPDAMOhBGWXar5Ce9N7qQURhwAZgsM0yiigOJ5NpL6M/vsZfFfr6HGItqELL4uik8HBS9GHwK3Q+DMHETwZy0NN02wDeMuAt49nX377QPffm+GwApF4DPiSlHl9DttSm43Tr8S30r1BLlAe6ajpEIh8eT7udl8XF3VHx4ztvnjjcfdB10qi4IOGfh+1QuFu8fubilx9ijq6HL/K1OZcDCYbEpEcKGdKjbKkLTb3VnrrAPU9fNkfduR9iGLymk+tSVXQK+gKqG9Arw8yHEs5CCgTgHnKzKs=2nJ9NBhX7TTT82Er9AHLJbPVWVBZYwVLHCI5oGX0ORk0j6IS0SH+9F5dRVF53oURWes45sZNNhFSmts4qB19SA==',
            'X-MERCHANT-ID': 'FXM',
            'X-ORG-ID': 'PHONEPE',
            'X-SOURCE-LOCALE': 'zh',
            'X-SOURCE-PLATFORM': 'Android',
            'X-SOURCE-TYPE': 'APP',
            'X-SOURCE-VERSION': '24011907',
            'accept': 'application/json',
        },
        "data": {
            'authTokenInfo': {
                'tokenType': 'USER_AUTH_TOKEN'
            },
            'userInfo': {
                'number': str(random.randint(1000000000, 9999999999)),
                'countryCode': 91,
                'region': 'IN',
                'userInfoType': 'PHONE_V2',
            }
        },
        'method': 'post',
        'status_code': 200,
    },
    'indian_socks_ip_amazon': {
        'url': 'https://www.amazon.in/upi/receive-payment?ref_=apay_account_myqr',
        'headers': {
              'Cookie': 'csm-hit=AQ5QPVAW95KPVVCBA2FT+sa-DQGDTZRQDM2KY7MZZED7-Z41J2ADX4JWOYP4M0A6V|1745223098492; at-acbin=Atza|IwEBIO8aw2Jp2bTFOwY_Vm05gqVdU1GY4L_BMKipy521Bs8DOGFX7vrmib1goIZgu2TnTgQTj_BUCjaprtnDuQnwmul6v5TDWR3DcTiUOrI8AOYgqjQMeD6OPotMof_vL8OTtlHSSIhfYjGVag7zOZNBfSHCAo15ZJhnfbK_XQIHlWKKQCb-ivVnVbXqd3dfpxUkaZkeCCb2PL6ua9I5IidWTdy-oK_ewX7DBUs-Al3siagTyg; i18n-prefs=INR; lc-acbin=en_IN; sess-at-acbin="kDOedh/HeQZ72HHMclj1GW+1Wg6SP3YsE+lnSFXgLoE="; session-id=261-5322451-9989254; session-id-time=2082787201l; session-token="2wFkVONC0nNHhFe0TiHNSS+uhmFwaZuoB0KjgLExPYfcCT9pSFnb1QxR37Ct8gJ20kyj1OyodZrEm6rWF3uA3kV5oM56/xqFTDlUR0Ed5B3T7WEf8zgTWNT2HHNqWOjVyDP53lznKNnCm485vRVntCDKnzeEYa0yp1tWMGOh4wtV+MTzLlBAheGO1w7SqwAkqtbEnzmKKEQjEMDkag+Qksqemb1g769ySokcMJnuiUWoN9ElUUS9unHAg6tpRgqYyX/8s8UXti1XgkR4bZOcysSUc+fEUYQtujxTA6nAYjwPGG6tpp1rdSzz9BbX4DmPE6m8AG2UPZ0ZKo0Z+upHvTpQi5BH6Le+Rs93lxKWP6glsC/ArVOjmw=="; sst-acbin=Sst1|PQEWa9asSYY2F_OKZBPtwbS6CU5zBsyYW_k5RQNfShVAaB3PF4MhF_TfLIKcxN5ti6gWDgpV1lqfwZ-0i7hHnC6hDFpYqVULH6lFR_whbNhn64hp1GJ7FB_Bb92cpY9bOR3iiEGLqwkLtjcf_bYStm8Ylufzp3Jvd7FTGVZn4p-OUA_-5TTOnHoAE5istj5OrTx3Gki-Z1LqHSueA0WF13paWHncTZvZE5wgTKJlmgHo3t88E4hDALGSylVexj8yait5KfHYQQZ7KLNDJjjozwndeE31y_FyxNFW14JuDWABRGY; ubid-acbin=262-3636740-9831050; x-acbin=HOKyKBsNV17N0lCjefSoXlwOksNfxBP5G6tPELfGp2X1qc9VjLxy5XTmDKtgEwR9; id_pk=eyJuIjoiMCJ9; id_pkel=n0',
              'dpr': '1',
              'ect': '4g',
              'sec-ch-ua-mobile': '?0',
              'Sec-Fetch-User': '?1',
              'Referer': 'https://www.amazon.in/gp/sva/dashboard?ref_=nav_cs_apay',
              'Sec-Fetch-Dest': 'document',
              'rtt': '100',
              'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
              'sec-ch-ua-platform-version': '"7.0.0"',
              'viewport-width': '360',
              'Host': 'www.amazon.in',
              'Sec-Fetch-Mode': 'navigate',
              'Upgrade-Insecure-Requests': '1',
              'downlink': '6',
              'sec-ch-device-memory': '8',
              'sec-ch-dpr': '1',
              'sec-ch-ua-platform': '"Windows"',
              'Accept-Language': 'zh-CN,zh;q=0.9',
              'Accept-Encoding': 'gzip, deflate, br, zstd',
              'Connection': 'keep-alive',
              'Sec-Fetch-Site': 'same-origin',
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
              'device-memory': '8',
              'sec-ch-viewport-width': '360',
        },
        "data": {},
        'method': 'get',
        'status_code': 200,
    },
    'indian_socks_ip_airtel': {
        'url': 'https://app.airtelbank.com:5055/mobgw2/mobileswitch/api/v1/upi/customer/vpa/',
        'headers': {
              'Host': 'app.airtelbank.com:5055',
              'User-Agent': 'Airtel/4.99.7,ANDROID/13,Xiaomi/MI 8 Lite,XXHDPI',
              'Connection': 'Keep-Alive',
              'Accept-Encoding': 'gzip',
              'x-bsy-did': 'bhqfyt99rl8uygp2',
              'x-bsy-appvn': '4.99.7',
              'callingSource': 'ThanksApp',
              'x-bsy-utkn': 'YaIPduv61prr4xLnU0:k2a0tWZxcOTFMQDd/BhlTIMleOA=',
              'x-bsy-dt': '9lhj1miw',
              'contentId': 'AN26365858100',
              'Authorization': 'nE1ln4IBwgJB0bOAq1YAywTKVcQx5VnIKaFsSDw+GNwhvDsw0dLdoaoRyTfcOjsb+AB0q2zvgmcReSH+YIWipOedam5ZRyLidZ79MJyQvp3KVxPwvQVyY2jgiZ3a+tq1lBOukfTDr13ouuVrEacXNAd89ngTurd4EPk6q2oNjNqnuGoPk+3tYEm4L55pxCmOwKigFtopp2EcTSPBQID4Lcf71o/sCPhG4RDqS4y1o2J0d5JmdCA+fLPRwQEUqNcjEI4MPMpvT5q58c6aZrSDUcDX16m5CyCTd70opxH/NIb0mYyrd3Di598T43K9K3leFndZGBESwP3gt80+dLRv9Q=='
        },
        "data": {
            "data": f"{random.random()}|7781537675402928",  # 需改动
            "versionNo": '4072',  # 需改动
            "platform": "ANDROID"
        },
        'method': 'get',
        'status_code': 200,
    },
    'indian_socks_ip_mobi': {
        'url': 'https://appapi.mobikwik.com/p/upi/vpa/profile/v2',
        'headers': {
              'Authorization': 'WI8JPwmLxB6LV6LYKKcCow==.8r2cas362cavscuf0nu7b5bss8',
              'User-Agent': 'okhttp/4.12.0',
              'Host': 'appapi.mobikwik.com',
              'Content-Type': 'application/json; charset=utf-8',
              'X-Device-Details': 'bhqfyt99rl8uygp2',
              'X-Device-ID': 'FC2B656CA8382C5054909C5285399EC1AC8B28A9',
              'os-version': '33',
              'X-MClient': '3',
              'X-tune-limited-flag': '0',
              'os': 'Android 13',
              'appName': 'com.mobikwik_new',
              'X-App-Ver': '2037',
              'X-Device-Details': 'OnePlus : IN2010',
        },
        "data": {},
        'method': 'get',
        'status_code': 200,
    },
    'indian_socks_ip_freecharge': {
      'url': 'https://www.freecharge.in/rest/upi/v2/upistatus',
        'headers': {
              'User-Agent': 'okhttp/4.12.0',
              'Content-Type': 'application/json; charset=utf-8',
              'csrfRequestIdentifier': 'cfb51edb-efb5-438f-93d7-a50da8324723',
              'Cookie': '_ga=GA1.1.768328936.1706099429; moe_uuid=af80e942-62e3-45e7-b022-4527eb8ecaa2; _ga_Q9NVXVJCL0=GS1.1.1706099429.1.1.1706099537.0.0.0; app_fc=uE7hVQspD47b02A-fZuobIBqivXVp7LZG1pdiDikwYFzhdO2vvJvW0huVtomk3L2d8bmI-VA0nAJuqH7ns2Ry--C1A47ccn9_eBZk1-HX9o0qNLIIoXqxbtRF3q6k4mJ',
        },
        "data": {
            'device': {
                'app': '',
                'id': ''
            }
        },
        'method': 'post',
        'status_code': 200,
    },
    'indian_socks_ip_indus': {
        'url': 'https://indusupiprd.indusind.com/upi/api/checkDeviceIdWeb',
        'headers': {
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 13; 55041234C Build/TQ3A.230901.001)',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': 'cfb51edb-efb5-438f-93d7-a50da8324723',
            'body': '{"check_root_detection":false,"requestMsg":"7AE3DDF39585F221777AD87526060A15813C86592B0A213305D5E8603FB134793F4498EC3F3AD0C0162C1527F7CBD04A05DC825DBD5E98AE45F39485BA1DB3091CBE7AAEAFAD81292F24279B9BEEEF3B2045EB10601C46E9B12B93D4E7679E41311F3C25FA43AC978BC09B329176ED3E06C1275DDC3391F16F0E00522EBA477E2A6F1F2057D90140635E6E8A257091CA73B2AC2001C056CB7B50874F1780FD3A35D830B0AFB5348777DE0B2CA1ADD3060E797CB5CB38B6EBDAD3CDB57B289157FBD93455D8724BA4AD037DFFCC56D83378DD11B902323324B89F6DCDC95F1F664686A0E4B0559111F6E57208B0A57DF3DBDD49ED2DDEB9694C128497AF69BE34F0A73F89785AA72C4190D71F74D201AA122E2B34D461888F8490E36D413557DC59C69FCE19654D2BC782AA4EA0547007BA5FB0D2C12F1B837631F0C09360A070A5BFD3E71F5EB47D6F32C519ABA7441BAC46FE98F13BD52E649163923157F924F36D748588977CE3339DD2932AAFBD3ABD4B292713E101E21C3A0A633C4F3D23C9AC565B852B4FA16360E812E70D640060285DD43A58EC8D0AFE140F8DE588A048E22C73F89F1EADA3C8EA6942AE7958E475EBD16E581E6A19B12CFD1DC145432AC546CD8C859F6A707A09AF2B155AEE6F23D30DF5F3900B9077323A8ABD43A58C678BEFE4546AF4FDB852F070F4F0BC8968E35B6DCF13C003BC061832FDF23A9DEA03C0042D7DA15422116349918E107D3CF60E8AE30948E7851C8C445DA76549E77A19029C15DCF5556B650B6F79DCA888028621D3AE4173574F8949BDA7A3B200F2B5E9DDAA9A8CBDCA67E7B46AB1F316E4C3CD50172DD307B6184D62579237FB291D766DD45097A8E71B1A27DF95DE8F800976403023D612FD9D7FF09964142DF8AD1760106DDE13FFE45172F28F2CA6A4C7FB95C3BCAB43CA94D3A68F2C6DD68C7EFE370F07DE6AB3BC929FF588AB28E4D2B5BE20C38587D184880171FE1B6DC33D30D46D3EE6AE9D20B5265E7A32FEC4C6E89EC19CCF5A76D3EFD8DC89CEB33F188DF6E9F7AA76277BF42F428253DAFD25EED5A21D3EB8AA38FD6F24F3DA874FF9587FD56BA81677ABE8E320402B0F1DD31671376E11182C4BE2F0E4F84E8619A62FE0211134AD1A827D8ECE1D2AAC2FC1237BC67647C2D8390044F68D880827CED68531F8D69E1BE9A97593D9DFB532990220CA2E1DF0D74F5C28F724E6583973ECE994672C2E56632FDC13BAD64BC8060E233879CC2E91FF8D1B7042E465421229F73AB5CEC935B2FCD05AA91F0670071E07B11DE717284FDC360317E569D24844456F11DEC24637432FD6FE73936F9B09020599D9A17354238F537D3E81A8AE685D4B847572D351D4324EFBC1957DB2731001AAFEEB87A51EE4C3A6E92264E00A49B66489224DD119686F42650D6FE621471F35FEDA811077D542FECD10FF2AF67BD153CD4FCAB84FDEE1E7","pspId":"10001"}',
        },
        "data": {
            'requestInfo': {
                    'pspId': 10001,
                    'pspRefNo': 'INDBE09BCAD6B2334C789436C6728D'
                 },
            'deviceInfo': {
                     'deviceId': 'fdc3acb3935a6182',
                     'mobileNo': '918083066993',
                     'simId': 'fdc3acb3935a61822',
                     'oldMobileNo': '918083066993'
                 },
            'userInfo': {
                     'mobileNo': '918083066993',
                     'isMerchant': False,
                     'showMerchant': False,
                     'defVPAStatus': False
                 },
            'simStatus': 'SNM',
            'userMsg': 'Your device seems to be changed as per your records. Do you want to update your device details mapped to your account?',
            'flowSimId': 'fdc3acb3935a61822',
            'deviceStatus': 'DR',
            'status': 'S',
            'statusDesc': 'SUCCESS',
            'addInfo': {
                'addInfo9': 'NA',
                'addInfo10': 'NA'
            },
            'isMerchant': False,
            'safetynet_response': {
                'timestampMs': 0,
                'ctsProfileMatch': False,
                'basicIntegrity': False,
                'appIntegrity': False
            },
            'check_root_detection': False,
            'reVerify': 'Y'
        },
        'method': 'post',
        'status_code': 200,
    },
    'indian_socks_ip_maha': {
          'url': 'https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request',
          'headers': {
                'Content-Type': 'application/json; charset=UTF-8',
                'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 13; IN2010 Build/TQ3A.230901.001.B1)',
          },
          "data": {
                    "data1": json.dumps({
                        "action": "AccountEnquiry",
                        "subAction": "AccountEnquiry",
                        "entityID": "BOM",
                        "inputParam": {
                            "mobileNo": str(random.randint(1000000000, 9999999999)),
                            "accountno": str(random.randint(1000000000, 9999999999)),
                            "entityId": "BOM",
                            "language": "en_US"
                        },
                        "mobileNo": str(random.randint(1000000000, 9999999999)),
                        "sessionId": str(random.randint(1000000000, 9999999999)),
                        "customerId": str(random.randint(1000000000, 9999999999)),
                        "deviceId": str(random.randint(1000000000, 9999999999)),
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": str(random.randint(1000000000, 9999999999)),
                        "mobileNo": str(random.randint(1000000000, 9999999999)),
                        "st": str(random.randint(1000000000, 9999999999)),
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{str(random.randint(1000000000, 9999999999)) or 'null'}|{str(random.randint(1000000000, 9999999999))}|{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}|MBANKING|AccountEnquiry"
          },
          'method': 'maha', #maha比较特殊，必须使用SOCKSProxyManager才能访问成功
          'status_code': 200,
    },
}


def main():
    try:
        rds = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
    except Exception as e:
        logging.exception('连接redis或数据库错误')
        return

    try:
        # 检测进程，如果已经运行，则直接退出
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if 'check_proxy.py' in proc.info['cmdline'] and current_pid != proc.pid:
                logging.info(f"check_proxy进程已存在， PID: {proc.info}")
                exit(0)  # 直接退出，避免多次执行

        for key, value in check_urls.items():
            proxies = rds.get(key)
            invalid_proxies = []  # 无效的ip
            valid_proxies = []  # 有效的ip
            if proxies is not None:
                proxies = proxies.decode().split(',')
                for proxy in proxies:
                    if not proxy:
                        continue
                    res = check_proxies(proxy, key, value)
                    if res:
                        valid_proxies.append(proxy)
                    else:
                        invalid_proxies.append(proxy)
                        # 通知检测到的失败代理ip
                        last_notification_time = rds.get(f"notification:{proxy}")
                        if last_notification_time is None or int(time.time()) - int(last_notification_time) > NOTIFY_TIME:
                            message = f"{key} {proxy} is invalid_{time.strftime('%Y-%m-%d %H:%M:%S')}"
                            if not send_notification(message):
                                send_notification(message)
                            rds.set(f"notification:{proxy}", int(time.time()))
                    time.sleep(1)
                valid_proxies = list(dict.fromkeys(valid_proxies))
                invalid_proxies = list(dict.fromkeys(invalid_proxies))
                logging.info(f"{key} 有效ip:{len(valid_proxies)}个, {','.join(valid_proxies)}")
                logging.info(f"{key} 无效ip:{len(invalid_proxies)}个 {','.join(invalid_proxies)}")
                #如果低于多少，直接通知
                if len(valid_proxies) < IP_LOWER:
                    message = f"{key} {len(valid_proxies)}个代理ip低于{IP_LOWER}，请手动添加代理ip，{time.strftime('%Y-%m-%d %H:%M:%S')}"
                    if not send_notification(message):
                        send_notification(message)
                # 检查是否需要拉取新的ip
                if len(valid_proxies) < IP_AT_LEAST and IF_get_new_proxies == True:
                    new_proxies = get_new_proxies()
                    if new_proxies:
                        logging.info(f"new_{key} 拉取到的ip:{len(new_proxies)}个, {','.join(new_proxies)}")
                        # 检测拉取到的代理ip
                        new_valid_proxies = []
                        new_invalid_proxies = []
                        for proxy in new_proxies:
                            if not proxy:
                                continue
                            res = check_proxies(proxy, key, value)
                            if res:
                                new_valid_proxies.append(proxy)
                            else:
                                new_invalid_proxies.append(proxy)
                        # 合集
                        valid_proxies = list(set(new_valid_proxies) | set(valid_proxies))
                        logging.info(f"new_{key} 总的有效的ip:{len(valid_proxies)}个, {','.join(valid_proxies)}")
                    else:
                        logging.error(f"new_{key} 拉取ip失败: {new_proxies}")
                        # 通知拉取失败
                        last_notification_time = rds.get(f"notification:get_new_proxies")
                        if last_notification_time is None or int(time.time()) - int(last_notification_time) > NOTIFY_TIME:
                            message = f"new_{key} 拉取ip失败: {new_proxies}_{time.strftime('%Y-%m-%d %H:%M:%S')}"
                            if not send_notification(message):
                                send_notification(message)
                            rds.set(f"notification:get_new_proxies", int(time.time()))
                    # 如果低于多少，直接通知
                    if len(valid_proxies) < IP_LOWER:
                        message = f"拉取新代理ip之后 {key}  {valid_proxies}个代理ip低于{IP_LOWER}，请手动添加代理ip，{time.strftime('%Y-%m-%d %H:%M:%S')}"
                        if not send_notification(message):
                            send_notification(message)
                rds.set(key, ','.join(valid_proxies))  # 如果不直接更新，则每2个小时通知一次
            else:
                logging.error(f'{key} 无代理{key}')
                # 通知拉取失败
                message = f"{key} 无代理ip，请手动添加代理ip，{time.strftime('%Y-%m-%d %H:%M:%S')}"
                if not send_notification(message):
                    send_notification(message)

            # 如果有备用的key，例如：indian_socks_ip_jio_backup，通过手动保存到redis，需要先检测再放入正式的key
            prod_key = key
            key = f"{key}_backup"
            proxies = rds.get(key)
            if proxies is not None:
                proxies = proxies.decode().split(',')
                invalid_proxies_backup = []  # 无效的ip
                valid_proxies_backup = []  # 有效的ip
                for proxy in proxies:
                    if not proxy:
                        continue
                    res = check_proxies(proxy, key, value)
                    if res:
                        valid_proxies_backup.append(proxy)
                    else:
                        invalid_proxies_backup.append(proxy)
                        # 通知检测到的失败代理ip
                        last_notification_time = rds.get(f"notification:{proxy}")
                        if last_notification_time is None or int(time.time()) - int(
                                last_notification_time) > NOTIFY_TIME:
                            message = f"{key} {proxy} is invalid_{time.strftime('%Y-%m-%d %H:%M:%S')}"
                            if not send_notification(message):
                                send_notification(message)
                            rds.set(f"notification:{proxy}", int(time.time()))
                    time.sleep(1)
                logging.info(f"{key} 有效ip:{len(valid_proxies_backup)}个, {','.join(valid_proxies_backup)}")
                logging.info(f"{key} 无效ip:{len(invalid_proxies_backup)}个 {','.join(invalid_proxies_backup)}")
                # 将有效的ip附加写入到正式的key
                union_values = list(set(valid_proxies) | set(valid_proxies_backup))
                logging.info(f"{key} {prod_key} 总有效ip:{len(union_values)}个, {','.join(union_values)}")
                rds.set(prod_key, ','.join(union_values))  # 取两个list的合集
            else:
                logging.error(f'{key} 备用无代理{key}')
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('main 脚本运行错误\n{}\n{}'.format(e, error_message))

def check_proxies(proxy, key, value):
    try:
        session = requests.Session()
        _proxy_ip = parse_ip(proxy)
        status_code_is_ok = False
        for i in range(RETRY_TIMES):
            try:
                if value['method'] == 'post':
                    data = json.dumps(value['data'])
                    response = session.post(value['url'], headers=value['headers'], data=data, proxies=_proxy_ip, timeout=10, verify=False)
                    logging.info(f"{key} {value['url']}, 代理ip:{_proxy_ip}响应码： {response.status_code}，结果：{response.text}")
                elif value['method'] == 'get':
                    response = session.get(value['url'], headers=value['headers'], proxies=_proxy_ip, timeout=10, verify=False)
                    logging.info(f"{key} {value['url']}, 代理ip:{_proxy_ip}响应码： {response.status_code}，结果：{response.text}")
                elif  value['method'] == 'maha':    # maha比较特殊，必须使用SOCKSProxyManager才能访问成功
                    from urllib3.contrib.socks import SOCKSProxyManager
                    import ssl
                    import urllib3
                    def create_ssl_context():
                        # 创建自定义SSL上下文
                        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
                        context.options |= ssl.OP_NO_SSLv2
                        context.options |= ssl.OP_NO_SSLv3
                        context.options |= ssl.OP_NO_COMPRESSION
                        context.options |= 0x4  # SSL_OP_LEGACY_SERVER_CONNECT
                        context.verify_mode = ssl.CERT_NONE
                        context.check_hostname = False
                        context.set_ciphers('ALL:@SECLEVEL=0')
                        return context

                    ssl_context = create_ssl_context()
                    # 创建SOCKS代理管理器
                    proxy_manager = SOCKSProxyManager(
                        proxy_url='socks5h://ceshi:ceshi@35.200.250.77:13563',
                        ssl_context=ssl_context,
                        retries=urllib3.Retry(2),
                        timeout=urllib3.Timeout(connect=30, read=30)
                    )
                    response = proxy_manager.request('POST', value['url'], headers=value['headers'])
                    logging.info(f"{key} {value['url']}, 代理ip:{_proxy_ip}响应码： {response.status}，结果：{response.data}")
                # if response.status_code == value['status_code']:  # 有可能不需要这个，只要能执行完毕，都不算被墙，或者有些返回特定的status_code 也算被墙
                #     status_code_is_ok = True
                #     break
                status_code_is_ok = True
                logging.info(f"第{i + 1}次 {key} {proxy}")
                break
            except Exception as e:
                logging.error(f"第{i + 1}次 {key} Error with proxy {proxy}: {str(e)}")
        return status_code_is_ok
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('check_proxies 脚本运行错误\n{}\n{}'.format(e, error_message))
        return False

def send_notification(message=""):
    try:
        url = f"https://exchange2.hlsj79.com/bot.php?key=12784569juufdaoufo45981gf89562&id=1626633374&text={urllib.parse.quote(message)}&type=1"
        requests.post(url)
        return True
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('send_notification 脚本运行错误\n{}\n{}'.format(e, error_message))
        return False

def parse_ip(ip_str: str):
    try:
        # ceshi:ceshi@34.93.250.99:13563
        user_pass, ip_port = ip_str.split('@')
        ip, port = ip_port.split(':')
        return {
            'http': f'socks5://{user_pass}@{ip}:{port}',
            'https': f'socks5://{user_pass}@{ip}:{port}',
        }
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('parse_ip 脚本运行错误\n{}\n{}'.format(e, error_message))
        return None

# 拉取新的ip
def get_new_proxies(if_try = 1):
    if if_try > 2:
        logger.error(f"获取代理ip: 超过{if_try}次，不再尝试")
        return []
    """从IPRoyal API获取代理列表"""
    try:
        # 设置API请求头
        headers = {
            "X-Access-Token": API_KEY,
            "Content-Type": "application/json"
        }

        # 获取订单列表
        url = f"{API_BASE_URL}/orders"
        params = {
            'product_id': PRODUCT_ID,
            'page': 1,
            'per_page': IP_GET_AT_ONE_TIME
        }

        logger.info(f"获取代理ip: URL={url}, 参数={params}, 第{if_try}次")
        session = requests.Session()
        response = session.get(url, headers=headers, params=params, timeout=15)
        # print(response.text, response.status_code)
        # exit()
        if response.status_code != 200:
            logger.error(f"获取代理ip失败: 状态码={response.status_code}, 响应={response.text}, 第{if_try}次")
            if_try = if_try + 1
            get_new_proxies(if_try)
            return []

        logger.info(f"获取代理ip: 状态码={response.status_code}, 响应={response.text}, 第{if_try}次")
        # 解析响应
        data = response.json()
        # 提取订单
        orders = []
        if isinstance(data, dict) and "data" in data:
            orders = data["data"]
        elif isinstance(data, list):
            orders = data

        if not orders:
            logger.warning("获取代理ip: 未找到ip")
            if_try = if_try + 1
            get_new_proxies(if_try)
            return []

        logger.info(f"成功获取 {len(orders)} 个订单")
        # socks5://ceshi:ceshi@34.93.219.182:13563
        ips = []
        for order in orders:
            for i in order['proxy_data']['proxies']:
                ip = f"{i['username']}:{i['password']}@{i['ip']}:{order['proxy_data']['ports']['socks5']}"
                ips.append(ip)

        if ips:
            logger.info(f"获取到新代理ip: {len(ips)}个 {ips}, 第{if_try}次")
            return ips
        else:
            logger.warning("未从订单中提取到代理")
            return []
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logging.error('get_proxy_list 获取代理列表失败 脚本运行错误\n{}\n{}'.format(e, error_message))
        if_try = if_try + 1
        get_new_proxies(if_try)
        return []

if __name__ == '__main__':
    main()
