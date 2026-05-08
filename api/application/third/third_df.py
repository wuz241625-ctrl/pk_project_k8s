import decimal
import json
import logging
import random
import string
import time
import uuid
import hashlib
import ipaddress
from urllib import parse
from urllib.parse import urlencode, quote

import pytz
import requests
import asyncio

from datetime import datetime

from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from application.base import BaseHandler
from application.timezone import display_now
from application.sign import SignatureAndVerification
from application.message import msg
from application.websocket.callback import success_third_df, cancel_third_df, revert_third_df
from urllib3.util.retry import Retry
from urllib.parse import urlparse


class AGDF_Pay(BaseHandler):
    async def post(self):
        df_name = "AGDF"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            # 总是出现 tornado.general:Invalid x-www-form-urlencoded body: 'latin-1' codec can't encode characters in position 0-1: ordinal not in range(256)的问题，故重新解析
            # uri_arguments = parse_qs_bytes(self.request.body.decode('latin-1'), keep_blank_values=True)
            # data_receive = {k: uri_arguments[k][0].decode('utf-8') for k in uri_arguments}

            data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])
        if not SignatureAndVerification.md5_verify(data, sign, mc_key, 'AGDF_notify'):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if not data['status'] in ["PAID", "CANCEL", "REVERT", "FINISH"]:
            return self.write('not success or not fail')

        if not mer_id == data['clientCode']:
            return self.write('merchantno error')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['clientNo'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['clientNo']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if data['status']== "REVERT" and _order_info[0]['status'] in [-1,-2]:
            self.logger.error('%s-REVERT 订单已经回调过 %s,REVERT成功' % (df_name, data['clientNo']))
            return self.write('ok')

        if not data['status']== "REVERT" and _order_info[0]['status'] in [3,4,-1,-2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['clientNo']))
            return self.write('ok')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['clientNo']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['clientNo']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['payAmount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['clientCode'] = mer_id
        data_post['clientNo'] = data['clientNo']
        sign = SignatureAndVerification.md5_sign(data_post, mc_key, "AGDF_query")
        sign = sign.lower()
        r_t[0]['query_url'] = r_t[0]['query_url'] + '?clientCode=' + mer_id + '&clientNo=' + data['clientNo'] + '&sign=' + sign
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            r = s.get(r_t[0]['query_url'], timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['clientNo'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['clientNo'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['clientNo'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')
        if ret['success'] is True:
            if not ret['data']['status'] == data['status']:
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['clientNo'], ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=data['clientNo'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if data['status'] == "PAID":  # 成功
            # if not await success_third_df(self, data['clientNo'], r_t[0]['pay_name_zh'], int(decimal.Decimal(data['amount']))/100, 4, None, df_name):
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['clientNo']))
                return self.write('confirm error')
            return self.write('ok')

        if data['status'] in ['CANCEL'] :  # 失败
            # if not await _cancel(self, data['clientNo'], r_t[0]['pay_name_zh'], '失败', 0):
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('ok')

        if data['status'] in ['REVERT'] :  # REVERT 成功后退回
            if not await revert_third_df(self, _order_info):
                return self.write('REVERT error')
            return self.write('ok')


class CUB_Pay(BaseHandler):
    async def post(self):
        df_name = "cubpay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            # 总是出现 tornado.general:Invalid x-www-form-urlencoded body: 'latin-1' codec can't encode characters in position 0-1: ordinal not in range(256)的问题，故重新解析
            # uri_arguments = parse_qs_bytes(self.request.body.decode('latin-1'), keep_blank_values=True)
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            # data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive[0]
            # sign = data.pop('sign')
            # sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        if not data['status'] in ["success", "failed"]:
            return self.write('not success or not fail')

        if data['status'] == "success":
            data['status'] = "1"
        if data['status'] == "failed":
            data['status'] = "2"

        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['transaction_id'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['transaction_id']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('ok')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        _order_info = _order_info[0]

        # 查询订单确保回调安全
        r_t[0]['query_url'] = r_t[0]['query_url'] + '?UserId=' + mer_id + '&OrderId=' + _order_info['code']
        self.logger.info('{df_name}-查询订单-发送地址{url}'.format(df_name=df_name, url=r_t[0]['query_url']))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json, text/javascript',
        }
        try:
            r = s.get(r_t[0]['query_url'], timeout=(5, 5), headers=headers, verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)[0]
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if 'status' in ret.keys():
            if not ret['status'] == data['status']:
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(ret['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['status'] == "1":  # 成功
            # if not await success_third_df(self, data['clientNo'], r_t[0]['pay_name_zh'], int(decimal.Decimal(data['amount']))/100, 4, None, df_name):
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('ok')

        if data['status'] in ['2']:  # 失败
            # if not await _cancel(self, data['clientNo'], r_t[0]['pay_name_zh'], '失败', 0):
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('ok')

class WALLET_Pay(BaseHandler):
    async def post(self):
        df_name = "wallet"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            # 总是出现 tornado.general:Invalid x-www-form-urlencoded body: 'latin-1' codec can't encode characters in position 0-1: ordinal not in range(256)的问题，故重新解析
            # uri_arguments = parse_qs_bytes(self.request.body.decode('latin-1'), keep_blank_values=True)
            # data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            # sign = data.pop('sign')
            # sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        if not data['status'] in ["Completed", "Failed"]:
            return self.write('not success or not fail')


        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['orderId'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['orderId']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('ok')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['secret_key'] = mc_key
        data_post['order'] = data['orderId']
        data_post = json.dumps(data_post, separators=(',', ':'))
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json','Content-Type': 'application/json',
        }
        try:
            r = s.post(r_t[0]['query_url'],data=data_post, timeout=(30, 30), headers=headers, verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')
        if 'status' in ret.keys() and ret['status'] is False:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not ret['data']['success'] is True:  # 成功
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')
        if not ret['data']['data']['status'] == data['status']:
            # 查询订单与回调的结果不一致
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致3，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))

        # if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(ret['data']['data']['amount']):
        #     self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
        #     return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['status'] == "Completed":  # 成功
            # if not await success_third_df(self, data['clientNo'], r_t[0]['pay_name_zh'], int(decimal.Decimal(data['amount']))/100, 4, None, df_name):
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('success')

        if data['status'] in ['Failed']:  # 失败
            # if not await _cancel(self, data['clientNo'], r_t[0]['pay_name_zh'], '失败', 0):
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class Haoda_Pay(BaseHandler):
    async def post(self):
        df_name = "haoda"
        ip = await self.get_ip()
        # 先获取参数，以便下一步筛选出付款账户
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 有多个付款账户，先筛选出付款账户
        sql_order_info = 'select otherpay_id from orders_df  where otherpay_code = %s'
        account_info = await self.query(sql_order_info, data['data']['payout_id'])
        if not account_info:
            self.logger.info('无此订单号信息：{} {}'.format(data['data']['payout_id'], df_name))
            return self.write('No payout id information')
        pay_id = account_info[0]['otherpay_id']

        sql_t = 'select id,mer_id,mer_key,mer_key2,pay_name,pay_name_zh,notify_ip,query_url from third_pay_df where id = %s'
        r_t = await self.query(sql_t, pay_id)

        df_name = r_t[0]['pay_name']

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        mer_key2 = r_t[0]['mer_key2']

        if not data['status'].lower() in ["success", "failed", "rejected"]:
            return self.write('not success or not fail')

        if data['status'].lower() in ["failed", "rejected"]:  # 失败
            data['status'] = "failed"

        # 防止生成订单即刻回调
        # time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['data']['payout_id'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['data']['payout_id']))

            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write({"status": "success", "message": "data received"})  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()
        data_post['payout_id'] = data['data']['payout_id']

        data_post = json.dumps(data_post)
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(
            df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                          'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                          'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                          'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                          'useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json', 'Content-Type': 'application/json',
            'x-client-id': mer_id,
            'x-client-secret': mer_key,
        }
        proxies = {
            'http': mer_key2,
            'https': mer_key2
        }
        try:
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(30, 30), headers=headers, verify=False, proxies=proxies)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not int(r.status_code) == requests.codes.ok:  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if 'status_code' in ret.keys() and str(ret['status_code']) != '200':  # 结果中的状态码非成功
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if ret['data']['status'].lower() in ["failed", "rejected"]:  # 失败
            ret['data']['status'] = "failed"
        if not ret['data']['status'].lower() == data['status'].lower():
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['data']['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['status'].lower() == "success":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write({"status": "success", "message": "data received"})
        if data['status'].lower() in ["failed", "rejected"] :  # 失败
            # if not await _cancel(self, data['clientNo'], r_t[0]['pay_name_zh'], '失败', 0):
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class HAPPY_Pay(BaseHandler):
    async def post(self):
        df_name = "happypay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:

            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 如果不在 1、2、3 、11 4、5 6、7、8 则无法判断成功或者失败
        # 把状态码转换为数字
        if data['data']['status'] not in [1, 2, 3, 11, 4, 5, 6, 7, 8]:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')



        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['data']['system_order_number'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['data']['system_order_number']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write({"status": "success", "message": "data received"})  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['data']['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['data']['order_number'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()

        data_post['username'] = mer_id
        data_post['order_number'] = data['data']['order_number']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key, "secret_key")
        data_post['sign'] = data_post['sign'].lower()
        # data_post = json.dumps(data_post)
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
                'Accept': 'application/json',
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(30, 30), headers=headers, verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)

        if not r.status_code == requests.codes.ok:
            # self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['clientNo'], r_t[0]['query_url'], r.status_code))
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if ret["http_status_code"] not in [200, 201]:  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["http_status_code"]))
            return self.write('error 响应码错误')

        if data['data']['status'] not in [1, 2, 3, 11, 4, 5, 6, 7, 8]:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not decimal.Decimal(ret['data']['status']) == decimal.Decimal(data['data']['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['data']['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['data']['status'] in [4, 5]:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write({"status": "success", "message": "data received"})

        if data['data']['status'] in [6, 7, 8]:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class King_Pay(BaseHandler):
    df_name = "kingpay"
    async def post(self):
        df_name = self.df_name
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        # 获取代付参数，mer_key2为服务端公钥，mer_key3为客户端私钥
        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_key2 = r_t[0]['mer_key2']
        mer_key3 = r_t[0]['mer_key3']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 验签
        is_verify = SignatureAndVerification.verify_sha256_sign(mer_key2, data, data['sign'])
        if not is_verify:
            self.logger.error('%s-验签错误， %s' % (df_name, data['sign']))
            return await self.json_response({'status': 'error', 'message': 'error 验签错误'})

        # 如果不在 1, 2, 3, 4, 5, 6, 7中 则无法判断成功或者失败
        # 把状态码转换为数字
        if data['status'] not in [1, 2, 3, 4, 5, 6, 7]:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        # time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['orderId'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['orderId']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write({"code": "0", "message": "success 1"})  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['withdrawAmount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['orderId'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        # data_post = dict()
        #
        # data_post['merchantId'] = mer_id
        # data_post['appId'] = mer_key
        # data_post['orderId'] = data['orderId']
        # data_post['outOrderId'] = data['outOrderId']
        # data_post['timestamp'] = int(round(time.time() * 1000))
        #
        # data_post['sign'] = SignatureAndVerification.sha256_sign(data_post, mer_key3)
        #
        # data_post = json.dumps(data_post)
        # self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # # 超时重试
        # s = requests.Session()
        # s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        # s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        # try:
        #     headers = {
        #         'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
        #                       'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
        #                       'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
        #                       'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
        #                       'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
        #                       'useStatusBar/true isConcaveScreen/false Region/CN',
        #         'Accept': 'application/json',
        #         'Content-Type': 'application/json'
        #     }
        #     r = s.post(r_t[0]['query_url'], data=data_post, timeout=(5, 10), headers=headers)
        # except Exception as e:
        #     self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
        #     return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        # s.close()
        # self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        # ret = json.loads(r.text)

        # if not r.status_code == requests.codes.ok:
        #     self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
        #     return self.write('error 查询第三方订单失败')
        #
        # if str(ret["code"]) != '0':  # 接口响应中的状态码非成功
        #     self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["http_status_code"]))
        #     return self.write('error 响应码错误')
        # # king pay status字段状态：
        # # 1、待审核；2、审核通过；3、渠道打款中；4、审核不通过；5、交易成功，已到账；6、交易失败；7、交易异常
        # if data['status'] not in [1, 2, 3, 4, 5, 6, 7]:
        #     self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
        #     return self.write('error 查询订单与回调结果不一致')
        # if not decimal.Decimal(ret['status']) == decimal.Decimal(data['status']):
        #     self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        #     return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['withdrawAmount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['status'] == 5:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write({"code": "0", "message": "success 2"})

        if data['status'] in [4, 6, 7]:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write({"code": "0", "message": "success 3"})


class King_Pay2(King_Pay):
    df_name = "kingpay2"


class Razo_Pay(BaseHandler):
    async def post(self):
        df_name = "razo"
        ip = await self.get_ip()
        # 先获取参数，以便下一步筛选出付款账户
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive.get('payload', {}).get('payout', {}).get('entity', {})
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 有多个付款账户，先筛选出付款账户
        sql_order_info = 'select otherpay_id from orders_df  where otherpay_code = %s'
        account_info = await self.query(sql_order_info, data['id'])
        if not account_info:
            self.logger.info('无此订单号信息：{} {}'.format(data['id'], df_name))
            return self.write('No payout id information')
        pay_id = account_info[0]['otherpay_id']

        sql_t = 'select id,mer_id,mer_key,mer_key2,pay_name,pay_name_zh,notify_ip,query_url from third_pay_df where id = %s'
        r_t = await self.query(sql_t, pay_id)

        df_name = r_t[0]['pay_name']

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        networks = [ipaddress.ip_network(ip, strict=False) for ip in ips]
        ip = ipaddress.ip_address(ip)
        if not any(ip in net for net in networks):
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        mer_key2 = r_t[0]['mer_key2']

        if not data['status'].lower() in ["processing", "processed", "reversed", "queued",
                                          "pending", "rejected", "cancelled", "failed"]:
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        # time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['id'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['id']))

            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write({"status": "success", "message": "data received"})  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        query_url = '{}?account_number={}'.format(r_t[0]['query_url'], mer_key2)

        params = {'reference_id': _order_info['code']}
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(
            df_name=df_name, url=query_url, data_post=params))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        try:
            r = s.get(query_url, params=params, headers=headers, auth=HTTPBasicAuth(mer_id, mer_key))
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not int(r.status_code) == requests.codes.ok:  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')

        if not ret['items']:
            self.logger.error('%s-查询订单%s,查询内容为空 %s %s' % (df_name, _order_info['code'], query_url, r.status_code))
            return self.write('error 查询内容为空')

        if ret['items'][0].get('status') not in ["processing", "processed", "reversed", "queued",
                                                 "pending", "rejected", "cancelled", "failed"]:  # 结果中的状态码获取失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not ret['items'][0].get('status') == data['status'].lower():
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(decimal.Decimal(_order_info['amount']) * 100) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['status'].lower() == "processed":  # 成功
            utr = ret['items'][0].get('utr')
            self.logger.error('{df_name}-订单{code},获取到utr为： {utr}'.format(df_name=df_name, code=_order_info['code'], utr=utr))
            if not await success_third_df(self, _order_info, utr):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write({"status": "success", "message": "data received"})
        if data['status'].lower() in ["reversed", "failed", "rejected"]:  # 失败
            # if not await _cancel(self, data['clientNo'], r_t[0]['pay_name_zh'], '失败', 0):
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class YD_Pay(BaseHandler):
    async def post(self):
        df_name = "ydpay"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        mer_key2 = r_t[0]['mer_key2']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        sign = data.pop('sign').upper()

        # 验签
        if not SignatureAndVerification.md5_verify(data, sign, mer_key):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if data['status_code'] not in ["success", "error"]:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['order_out_no'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['order_out_no']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('ok')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['order_amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['order_out_no'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_get = dict()
        data_get['order_out_no'] = data['order_out_no']
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_get))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        # 获取到mer_key2(代理)则组装代理参数
        proxies = None
        if mer_key2:
            proxies = {
                'http': mer_key2,
                'https': mer_key2
            }
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            r = s.get(r_t[0]['query_url'], params=data_get, timeout=(5, 10), headers=headers, verify=False, proxies=proxies)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)

        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["status"]) != 'success':  # 接口响应中的状态非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s massage: %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["status"], ret['message']))
            return self.write('error 响应码错误')
        # yd pay status字段状态：
        # 订单状态 0 创建中  1 付款中  2 付款成功 3 付款失败
        if str(data['order_status']) not in ['0', '1', '2', '3']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not decimal.Decimal(ret['data']['status']) == decimal.Decimal(data['order_status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['order_amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if str(data['order_status']) == '2':  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('ok')

        if str(data['order_status']) == '3':  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('ok')



class SD_Pay(BaseHandler):
    async def post(self):
        df_name = "sdpay"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        # 获取代付参数，mer_key2为服务端公钥，mer_key3为客户端私钥
        id = r_t[0]['id']
        # mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            params_str = self.request.body.decode()
            data_receive = {line.split('=')[0]: line.split('=')[1] for line in params_str.split('&')}
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 如果不在 1, 2, 3 中 则无法判断成功或者失败
        # 把状态码转换为数字
        if data['state'] not in ['1', '2', '3']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['order_no'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['order_no']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('Success')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['order_no'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_get = dict()
        data_get['id'] = mer_id
        data_get['order_no'] = data['order_no']

        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_get}'.format(df_name=df_name, url=r_t[0]['query_url'], data_get=data_get))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
            }
            r = s.get(r_t[0]['query_url'], params=data_get, timeout=(5, 10), headers=headers)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)

        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if not ret["status"]:  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], ret["status"]))
            return self.write('error 响应码错误')
        # sd pay state字段状态：
        # 订单状态 1:待支付, 2:成功, 3失败
        if ret['data']['state'] not in ['1', '2', '3']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not ret['data']['state'] == data['state']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(ret['data']['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['state'] == '2':  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('Success')

        if data['state'] == '3':  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('Success')


class Queen_Pay(BaseHandler):
    async def post(self):
        df_name = "queen"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        # 获取代付参数
        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = {}
            for key in self.request.arguments.keys():
                value = self.request.arguments.get(key)
                if value:
                    data_receive[key] = value[0].decode('utf-8')
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 支付结果：5 - 成功 : 3 – 失败
        # 把状态码转换为数字
        if str(data['status']) not in ['3', '5']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(2)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['order_id'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['order_id']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('SUCCESS')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['order_id'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()
        data_post['merchant'] = mer_id
        data_post['order_id'] = data['order_id']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key).lower()

        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(5, 10), headers=headers)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)

        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["status"]) == '0':  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["status"]))
            return self.write('error 响应码错误')
        # queen pay status字段状态：
        # 0-错误 1-等待中，2,6-进行中，3-失败，5-成功
        if str(data['status']) not in ['0', '1', '2', '3', '5', '6']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not decimal.Decimal(ret['status']) == decimal.Decimal(data['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if str(data['status']) == '5':  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('SUCCESS')

        if str(data['status']) in '3':  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('SUCCESS')


class IN_Pay(BaseHandler):
    async def post(self):
        df_name = "inpay"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        # 获取代付参数
        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 支付结果(中文状态)：已完成 失败
        if str(data['status']) not in ['已完成', '失败']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(2)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['bill_number'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['bill_number']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('OK')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['bill_number'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()
        data_post['client_id'] = mer_id
        data_post['bill_number'] = data['bill_number']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key).lower()
        data_post = json.dumps(data_post)

        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(5, 10), headers=headers)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)

        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["code"]) != '0':  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["status"]))
            return self.write('error 响应码错误')
        # inpay status字段状态：
        # 中文状态字段： '等待', '处理中', '已完成', '失败', '订单不存在'
        if str(data['status']) not in ['等待', '处理中', '已完成', '失败', '订单不存在']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not ret['status'] == data['status']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if str(data['status']) == '已完成':  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('OK')

        if str(data['status']) == '失败':  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('OK')


class RED_Pay(BaseHandler):
    async def post(self):
        df_name = "redpay"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        # 获取代付参数
        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = {key: self.get_argument(key) for key in self.request.arguments.keys() if self.get_argument(key)}
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 支付结果：1 成功 5驳回
        if str(data['refCode']) not in ['1', '5']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(2)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['out_trade_no'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['out_trade_no']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('OK')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['bill_number'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()
        data_post['mchid'] = mer_id
        data_post['out_trade_no'] = data['out_trade_no']
        data_post['pay_md5sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)
        # data_post = json.dumps(data_post)

        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
                'Accept': 'application/json',
                # 'Content-Type': 'application/json'
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(5, 10), headers=headers)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)

        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["status"]) != 'success':  # success为请求成功（不代表业务成功）
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["status"]))
            return self.write('error 响应码错误')
        # refCode字段状态： "1"=成功，"2"=失败，"3"=处理中
        if str(ret['refCode']) not in ['1', '2', '3']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        # 回调状态为： 1成功 5驳回；  查询状态为： 1成功  2失败  3处理中
        is_diff = False
        if str(data['refCode']) == '1' and str(ret['refCode']) != '1':
            is_diff = True
        if str(data['refCode']) == '5' and str(ret['refCode']) != '2':
            is_diff = True
        if is_diff:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if str(data['refCode']) == '1':  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write('OK')

        if str(data['refCode']) in ['2', '5']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('OK')


class LUCKY_Pay(BaseHandler):
    async def post(self):
        df_name = "lucky"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])
        if not SignatureAndVerification.md5_verify(data, sign, mc_key, 'AGDF_notify'):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if not data['status'] in ["PAID", "CANCEL", "REVERT", "FINISH"]:
            return self.write('not success or not fail')

        if not mer_id == data['clientCode']:
            return self.write('merchantno error')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['clientNo'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['clientNo']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if data['status'] == "REVERT" and _order_info[0]['status'] in [-1,-2]:
            self.logger.error('%s-REVERT 订单已经回调过 %s,REVERT成功' % (df_name, data['clientNo']))
            return self.write('ok')

        if not data['status'] == "REVERT" and _order_info[0]['status'] in [3,4,-1,-2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['clientNo']))
            return self.write('ok')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['clientNo']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['clientNo']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['payAmount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['clientCode'] = mer_id
        data_post['clientNo'] = data['clientNo']
        sign = SignatureAndVerification.md5_sign(data_post, mc_key, "AGDF_query")
        sign = sign.lower()
        # url需要拼接
        query_url = r_t[0]['query_url']
        query_url = query_url.format(clientCode=mer_id, clientNo=data['clientNo'], sign=sign)
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            r = s.get(query_url, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['clientNo'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['clientNo'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['clientNo'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')
        if ret['success'] is True:
            if not ret['data']['status'] == data['status']:
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['clientNo'], ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=data['clientNo'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if data['status'] == "PAID":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['clientNo']))
                return self.write('confirm error')
            return self.write('ok')

        if data['status'] in ['CANCEL']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('ok')

        if data['status'] in ['REVERT']:  # REVERT 成功后退回
            if not await revert_third_df(self, _order_info):
                return self.write('REVERT error')
            return self.write('ok')


class APay(BaseHandler):
    async def post(self):
        df_name = "apay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])
        if not SignatureAndVerification.md5_verify(data, sign, mc_key):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if not str(data['status']) in ["1", "2", "3"]:
            return self.write('not success or not fail')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['tradeNo'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['tradeNo']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3,4,-1,-2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['tradeNo']))
            return self.write('SUCCESS')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['tradeNo']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['tradeNo']))

        if not int(decimal.Decimal(_order_info[0]['amount']) * 100) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['tradeNo'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['cid'] = data['cid']
        data_post['tradeNo'] = data['tradeNo']
        data_post['type'] = '001'
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key)
        data_post['sign'] = data_post['sign'].lower()
        # url需要拼接
        query_url = r_t[0]['query_url']
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            r = s.post(query_url, data=data_post, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['tradeNo'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['tradeNo'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['tradeNo'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')

        # retcode错误码： 0 请求成功; 001	商户普通余额金额不足; 002 订单号重复; 004 验签失败; 005 参数错误; 006 无支付权限;
        # 007 系统繁忙（不可做失败处理）; 009 未配置通道、通道满额或金额不位于通道限额
        if ret['retcode'] == '0':
            if ret['status'] != data['status']:
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['tradeNo'], ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=data['tradeNo'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')
        # 1: 成功, 2: 处理中, 3: 失败
        if data['status'] == "1":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['tradeNo']))
                return self.write('confirm error')
            return self.write('SUCCESS')

        if data['status'] in ['3']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('SUCCESS')


class Globe(BaseHandler):
    async def post(self):
        df_name = "globe"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])
        if not SignatureAndVerification.md5_verify(data, sign, mc_key):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if not str(data['status']) in ["3", "4", "5"]:
            return self.write('not success or not fail')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['merchantOrderId'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['merchantOrderId']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3,4,-1,-2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['merchantOrderId']))
            return self.write('SUCCESS')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['merchantOrderId']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['merchantOrderId']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['applyAmount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['merchantOrderId'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['merchantCode'] = mer_id
        data_post['merchantOrderId'] = data['merchantOrderId']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key)
        data_post['sign'] = data_post['sign'].lower()
        data_post = json.dumps(data_post)
        # url需要拼接
        query_url = r_t[0]['query_url']
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        try:
            r = s.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['merchantOrderId'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['merchantOrderId'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['merchantOrderId'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')
        if ret['code'] == '00':
            if ret['data']['status'] != data['status']:
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['merchantOrderId'], ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=data['merchantOrderId'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')
        # status: 3 已完成  4 出款失敗  5 已沖正
        if data['status'] == "3":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['merchantOrderId']))
                return self.write('confirm error')
            return self.write('SUCCESS')

        if data['status'] in ['4']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('SUCCESS')


class Rupix(BaseHandler):
    async def post(self):
        df_name = "rupix"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            # data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])
        if not SignatureAndVerification.md5_verify(data, sign, mc_key):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if not str(data['status']) in ["success", "failed"]:
            return self.write('not success or not fail')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['outTradeNo'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['outTradeNo']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['outTradeNo']))
            return self.write('SUCCESS')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['outTradeNo']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['outTradeNo']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['outTradeNo'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['appId'] = mer_id
        data_post['outTradeNo'] = data['outTradeNo']
        data_post['nonceStr'] = ''.join(random.choice(string.ascii_letters) for _ in range(10))
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key)
        # url需要拼接
        query_url = r_t[0]['query_url']
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        try:
            r = s.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['outTradeNo'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['outTradeNo'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['outTradeNo'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')
        if str(ret.get('code')) == '200':
            if ret['data']['status'] != data['status']:
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['outTradeNo'], ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=data['outTradeNo'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')
        # status: 订单状态（success/failed）
        if data['status'] == "success":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['outTradeNo']))
                return self.write('confirm error')
            return self.write('SUCCESS')

        if data['status'] in ['failed']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('SUCCESS')


class Pay58pay(BaseHandler):
    async def get(self):
        df_name = "58pay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            # data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])
        if not SignatureAndVerification.md5_verify(data, sign, mc_key, key_name='secretKey'):
            self.logger.info('{df_name} sign error,{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            return self.write('sign error')

        if not str(data['status']) in ["1", "3", "5", "7"]:
            return self.write('not success or not fail')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['mchOrderNo'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['mchOrderNo']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['mchOrderNo']))
            return self.write('SUCCESS')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['mchOrderNo']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['mchOrderNo']))

        if not int(decimal.Decimal(_order_info[0]['amount']) * 100) == int(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['mchOrderNo'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['mchId'] = mer_id
        data_post['mchOrderNo'] = data['mchOrderNo']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key, key_name='secretKey')
        # url需要拼接
        query_url = r_t[0]['query_url']
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        data_post = json.dumps(data_post)
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        try:
            r = s.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['mchOrderNo'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['mchOrderNo'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['mchOrderNo'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')
        if str(ret.get('retCode')) == 'SUCCESS':
            if str(ret['status']) != str(data['status']):
                # 查询订单与回调的结果不一致
                self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['mchOrderNo'], ret=r.text))
                return self.write('error 查询订单与回调结果不一致')
        else:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=data['mchOrderNo'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')
        # status: 0-支付中，1-已完成，3-已超时，5-驳回中，7-已驳回。状态3，5，7都可以认为代付订单已经失败
        if str(data['status']) == "1":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['mchOrderNo']))
                return self.write('confirm error')
            return self.write('SUCCESS')

        if str(data['status']) in ['3', '5', '7']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('SUCCESS')


class Kuaiyinpay(BaseHandler):
    async def get(self):
        df_name = "kuaiyin"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mc_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            # data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            data_receive = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info('{df_name} 收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
            sign = data.pop('sign')
            sign = sign.upper()
        except Exception as e:
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        if not str(data['code']) in ["1000", '3000']:
            return self.write('not success')

        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['out_trade_no'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['out_trade_no']))
            return await self.json_response({'success': False, 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.error('%s-订单已经回调过 %s,确认成功' % (df_name, data['out_trade_no']))
            return self.write('success')

        if not _order_info[0]['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['out_trade_no']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['out_trade_no']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['out_trade_no'], ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        _order_info = _order_info[0]

        # 查询订单确保回调安全
        data_post = dict()
        data_post['out_trade_no'] = data['out_trade_no']

        headers = {
            'sid': mer_id,
            'nonce': str(uuid.uuid4()),
            'timestamp': str(int(round(time.time() * 1000))),
            'url': '/payfor/orderquery',
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
        headers['sign'] = SignatureAndVerification.md5_sign(sign_data, mc_key, key_name='KUAIYIN')

        # url
        query_url = r_t[0]['query_url']
        self.logger.info('{df_name}-查询订单-发送地址{url}，发送{data}'.format(df_name=df_name, url=r_t[0]['query_url'], data=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            r = s.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, data['out_trade_no'], query_url, e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=data['out_trade_no'], ret=r.text))
        ret = json.loads(r.text)
        # print(ret)
        if not r.status_code == requests.codes.ok:
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['out_trade_no'], query_url, r.status_code))
            return self.write('error 查询第三方订单失败')
        if not str(ret.get('code')) == '1000':
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name, code=data['out_trade_no'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致1')
        # 当code为1000时，订单状态变量存在： FAILURE代付失败  WAIT 等待付款  SUCCESS 代付成功  CLOSE失败关闭
        # 此支付只在查询结果中有状态参数status
        if str(ret['status']) == "SUCCESS":  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['out_trade_no']))
                return self.write('confirm error')
            return self.write('success')

        if str(ret['status']) in ['FAILURE', 'CLOSE']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class Wepay(BaseHandler):
    async def post(self):
        """ 处理 Wepay 代付异步通知，并查询订单状态 """
        df_name = "wepay"

        # 查询数据库，获取支付通道的配置信息
        sql_t = 'SELECT id, mer_id, mer_key, pay_name_zh, notify_ip, query_url FROM third_pay_df WHERE pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        self.logger.info(f"通知IP-源头: {notify_ips}")
        self.logger.info(f"通知IP-错误: {ip}")
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write("notify_ip error")

        try:
            # 解析 form-data 格式的请求数据
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info(f"{df_name} 收到回调参数: {data}, IP: {ip}")
            if "utr" in data:
                data.pop("utr")
            if "message" in data:
                data.pop("message")
            # 校验签名
            sign_valid = self.verify_md5_signature(data, mer_key)
            if not sign_valid:
                self.logger.error(f"{df_name}-错误: 签名验证失败")
                return self.write("sign error")
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 检查 tradeResult，判断订单状态
        trade_result = data["tradeResult"]

        if not str(trade_result) in ["1", "2", "3", "4"]:
            return self.write('not success')

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["merTransferId"])

        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['merTransferId']}")
            return self.write("error: no order")

        order_info = order_info[0]

        # 防止重复处理
        if order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['merTransferId']}")
            return self.write("success")

        # 确保 otherpay_id 匹配
        if order_info["otherpay_id"] != id:
            self.logger.error(f"{df_name}-错误: otherpay_id 不匹配 {data['merTransferId']}")
            return self.write("error: otherpay_id mismatch")

        # 确保金额一致
        if decimal.Decimal(order_info["amount"]) != decimal.Decimal(data["transferAmount"]):
            self.logger.error(f"{df_name}-错误: 金额不匹配 {data['merTransferId']}, 订单金额: {order_info['amount']}")
            return self.write("error: amount mismatch")

        # **新加：查询订单，确保回调数据的正确性**
        query_status = await self.query_order_status(mer_id, data["merTransferId"], mer_key, query_url)
        self.logger.error(f"{df_name}-查询订单返回值-{query_status}")
        self.logger.error(f"{df_name}-通知返回返回值-{trade_result}")
        if query_status is None:
            return self.write("error: query failed")
        if query_status != str(trade_result):
            self.logger.error(f"{df_name}-错误: 回调状态 {trade_result} 与查询状态 {query_status} 不一致")
            return self.write("error: status mismatch")

        # 根据 tradeResult 处理订单状态
        if str(trade_result) == "1":  # 代付成功
            if not await success_third_df(self, order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['merTransferId']))
                return self.write('confirm error')
            return self.write('success')

        elif str(trade_result) in ["2", "3"]:  # 代付失败 / 拒绝
            if not await cancel_third_df(self, order_info):
                return self.write('cancel error')
            return self.write('success')

        elif str(trade_result) == "4":  # 处理中
            self.logger.info(f"{df_name}-订单处理中: {data['merTransferId']}")
            return self.write("success")

        else:
            self.logger.warning(f"{df_name}-未知 tradeResult 值: {trade_result}")
            return self.write("error: invalid tradeResult")

    async def query_order_status(self, mch_id, mer_transfer_id, mch_key, query_url):
        """ 发送代付查询请求，返回订单状态 """
        
        """
        代付订单查询
        :param mch_id: 商户号
        :param mch_transferId: 商家转账单号
        :param query_url: 查询接口地址
        :param private_key: 商户密钥
        :return: 查询结果
        """
        params = {
            "mch_id": mch_id,
            "mch_transferId": mer_transfer_id,
            "sign_type": "MD5",
        }
        
        # 生成 MD5 签名
        params["sign"] = self.generate_md5_sign(params, mch_key)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        s = requests.Session()
        s.mount("http://", HTTPAdapter(max_retries=3))
        s.mount("https://", HTTPAdapter(max_retries=3))

        try:
            response = s.post(query_url, data=urlencode(params), headers=headers, timeout=(5, 5))
            self.logger.info(f"查询订单 {mer_transfer_id}, 返回结果: {response.text}")

            if response.status_code != 200:
                self.logger.error(f"查询订单 {mer_transfer_id} 失败，HTTP 状态码: {response.status_code}")
                return None

            res_data = response.json()
            if res_data.get("respCode") != "SUCCESS":
                self.logger.error(f"查询订单 {mer_transfer_id} 失败, 返回: {res_data}")
                return None

            return str(res_data.get("tradeResult"))  # 返回交易状态

        except Exception as e:
            self.logger.error(f"查询订单 {mer_transfer_id} 发生异常: {e}")
            return None

        finally:
            s.close()

    def generate_md5_sign(self, params, private_key):
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

    def verify_md5_signature(self, params, private_key):
        """
        校验 MD5 签名
        :param params: 回调参数 (dict)
        :param private_key: 商户私钥
        :return: bool
        """
        # 过滤掉 sign 和 signType
        filtered_params = {k: v for k, v in params.items() if k not in ["sign", "signType"]}

        # 按 ASCII 码排序并拼接
        sorted_params = sorted(filtered_params.items())
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        # 拼接密钥
        query_string += f"&key={private_key}"

        self.logger.info(f"[wepay] 计算签名字符串: {query_string}")

        # 计算 MD5 并转换为小写
        calculated_sign = hashlib.md5(query_string.encode('utf-8')).hexdigest().lower()

        # 比较签名
        return calculated_sign == params.get("sign", "").lower()

class Lemonpay(BaseHandler):
    async def post(self):
        """ 处理 LemonPay 代付异步通知，并查询订单状态 """
        df_name = "lemonpay"

        # 查询数据库，获取支付通道的配置信息
        sql_t = 'SELECT id, mer_id, mer_key, pay_name_zh, notify_ip, query_url FROM third_pay_df WHERE pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write("notify_ip error")

        try:
            # 解析 POST JSON 请求数据
            data = json.loads(self.request.body)  # 将请求体中的 JSON 数据解析为字典
            self.logger.info(f"{df_name} 收到回调参数: {data}, IP: {ip}")

            # 校验签名
            if not self.lemon_verify_md5_signature(data, mer_key):
                self.logger.error(f"{df_name}-错误: 签名验证失败")
                return self.write("sign error")
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # if not str(data['code']) in ["0", '1']:
        #     return self.write('not success')

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["merchant_order"])

        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['merchant_order']}")
            return self.write("error: no order")

        order_info = order_info[0]

        # 防止重复处理
        if order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['merchant_order']}")
            return self.write("SUCCESS")

        if not order_info['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['serial_number']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['serial_number']))

        # 确保金额一致
        if decimal.Decimal(order_info["amount"]) != decimal.Decimal(data["coin"]) / 100:
            self.logger.error(f"{df_name}-错误: 金额不匹配 {data['merchant_order']}, 订单金额: {order_info['amount']}")
            return self.write("error: amount mismatch")

        # 查询订单，确保回调数据的正确性
        query_status = await self.query_order_status(mer_id, data["merchant_order"], mer_key, query_url)
        self.logger.error(f"query_status={query_status}")
        self.logger.error(f"code={data["code"]}")
        # if query_status is None or str(query_status) != str(data["code"]):
        #     self.logger.error(f"{df_name}-错误: 订单查询状态与回调状态不一致")
        #     return self.write("error: status mismatch")

        # 处理订单状态
        if query_status == "1":  # 代付成功
            self.logger.info(f"{df_name}-订单代付成功: {data['merchant_order']}")
            if not await success_third_df(self, order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=data['merchant_order']))
                return self.write('confirm error')
            return self.write('success')

        # elif data["code"] in [0, 2]:  # 代付失败 / 驳回
        #     self.logger.info(f"{df_name}-订单代付失败: {data['merchant_order']}")
        #     if not await cancel_third_df(self, order_info):
        #         return self.write('cancel error')
        #     return self.write('success')
        elif query_status == "3" or query_status is None:  # 处理中
            self.logger.info(f"{df_name}-订单处理中: {data['merchant_order']}")
            return self.write("success")

        else:
            self.logger.info(f"{df_name}-订单代付失败: {data['merchant_order']}")
            if not await cancel_third_df(self, order_info):
                return self.write('cancel error')
            return self.write('success')
            # self.logger.warning(f"{df_name}-未知 code 值: {data['code']}")
            # return self.write("error: invalid code")

    async def query_order_status(self, merchant_num, merchant_order, merchant_key, query_url):
        """ 发送订单查询请求，返回订单状态 """
        # 获取当前时间，并格式化为 'YYYY-MM-DD HH:MM:SS'
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        params = {
            "merchant_num": merchant_num,
            "merchant_order": merchant_order,
            "find_date": current_time,
        }
        params["sign"] = self.generate_md5_sign(params, merchant_key)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = requests.post(query_url, data=urlencode(params), headers=headers, timeout=5)
            if response.status_code != 200:
                self.logger.error(f"查询订单 {merchant_order} 失败，HTTP 状态码: {response.status_code}")
                return None

            res_data = response.json()
            self.logger.info(f"请求地址: {query_url} 参数: {params}, res_data: {res_data}")
            return str(res_data["data"]['state'])  # 返回 1=成功, 2=驳回, 3=处理中
        except Exception as e:
            self.logger.error(f"查询订单 {merchant_order} 发生异常: {e}")
            return None

    def generate_md5_sign(self, params, private_key):
        """ 生成 MD5 签名 """
        # 过滤空值
        filtered_params = {k: v for k, v in params.items() if v}

        # 按 ASCII 排序
        sorted_params = sorted(filtered_params.items())

        # 拼接参数
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        # 拼接 key
        query_string += f"&key={private_key}"

        # 计算 MD5 并转大写
        return hashlib.md5(query_string.encode('utf-8')).hexdigest().upper()

    def lemon_verify_md5_signature(self, params, private_key):
        """ 校验 MD5 签名 """
        logging.info(f'params={params}')
        logging.info(f'private_key={private_key}')
        # 过滤 sign 字段
        filtered_params = {k: v for k, v in params.items() if k != "sign" and v}

        # 按 ASCII 排序
        sorted_params = sorted(filtered_params.items())

        # 拼接参数
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        # 拼接 key
        query_string += f"&key={private_key}"

        logging.info(f'Lquery_string={query_string}')
        # 计算 MD5 并转大写
        calculated_sign = hashlib.md5(query_string.encode('utf-8')).hexdigest().upper()
        
        logging.info(f'calculated_sign-{calculated_sign}')
        
        return calculated_sign == params.get("sign", "").upper()


class Pay777Pay(BaseHandler):
    async def post(self):
        df_name = "pay777pay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        if data['order_status'] not in ['WAIT_CONFIRM', 'WAIT_PAY', 'PAY_ING', 'PAY_FAIL', 'PAY_SUCCESS']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['system_order_id'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['system_order_id']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('success')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['merchant_order_id'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()

        data_post['app_id'] = mer_id
        data_post['merchant_order_id'] = _order_info['code']
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key)
        data_post['sign'] = data_post['sign'].lower()
        # data_post = json.dumps(data_post)
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(30, 30), headers=headers, verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)
        if not r.status_code == requests.codes.ok:
            # self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['clientNo'], r_t[0]['query_url'], r.status_code))
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["code"]) != '200':  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["http_status_code"]))
            return self.write('error 响应码错误')

        if data['order_status'] not in ['WAIT_CONFIRM', 'WAIT_PAY', 'PAY_ING', 'PAY_FAIL', 'PAY_SUCCESS']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not ret['data']['order_status'] == data['order_status']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['order_status'] in ['PAY_SUCCESS']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("success")

        if data['order_status'] in ['PAY_FAIL']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class SwiftPay(BaseHandler):
    async def post(self):
        df_name = "swiftpay"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_key2 = r_t[0]['mer_key2']
        mer_key3 = r_t[0]['mer_key3']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        if str(data['status']) not in ['0', '1', '2', '3']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(5)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where otherpay_code = %s'
        _order_info = await self.query(sql_order_info, data['payoutNo'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['orderId']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('success')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['payment']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['orderId'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()

        data_post['merchantNo'] = mer_id
        data_post['orderId'] = _order_info['code']
        data_post['sign'] = SignatureAndVerification.sha1_sign(data_post, mer_key3)
        data_post = json.dumps(data_post)
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                'Content-Type': 'application/json',
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(30, 30), headers=headers, verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)
        if not r.status_code == requests.codes.ok:
            # self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['clientNo'], r_t[0]['query_url'], r.status_code))
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["errNo"]) != '0':  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["http_status_code"]))
            return self.write('error 响应码错误')

        if str(ret['data']['status']) not in ['0', '1', '2', '3']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not str(ret['data']['status']) == str(data['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(ret['data']['payment']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if str(data['status']) in ['2']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("success")

        if str(data['status']) in ['3']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')


class LemonPay2(BaseHandler):
    async def post(self):
        df_name = "lemonpay2"
        sql_t = 'select id,mer_id,mer_key,mer_key2,mer_key3,pay_name_zh,notify_ip,query_url from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.info('无回调通知ip，请加回调通知ip {}'.format(df_name))
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.info('回调通知ip({})不在允许IP列表中:({}){}'.format(str(ip), str(ips), df_name))
            return self.write('notify_ip error')

        id = r_t[0]['id']
        mer_key = r_t[0]['mer_key']
        mer_key2 = r_t[0]['mer_key2']
        mer_key3 = r_t[0]['mer_key3']
        mer_id = r_t[0]['mer_id']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data_receive), ip=ip))
            data = data_receive
        except Exception as e:
            # 打印获取到的参数
            self.logger.exception('参数异常')
            return await self.json_response(msg[10000])

        # 验签
        is_verify = SignatureAndVerification.verify_sha256_sign(mer_key2, data, data['sign'])
        if not is_verify:
            self.logger.error('%s-验签错误， %s' % (df_name, data['sign']))
            return await self.json_response({'status': 'error', 'message': 'error 验签错误'})

        if data['result'] not in ['success', 'fail', 'waiting']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')

        # 防止生成订单即刻回调
        time.sleep(1)
        # 若订单已经成功了，则直接返回回调成功
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df  where code = %s'
        _order_info = await self.query(sql_order_info, data['order_no'])
        if not _order_info:
            self.logger.error('%s-错误，无此订单 %s' % (df_name, data['order_no']))
            return await self.json_response({'status': 'error', 'message': 'error 无此订单'})

        if _order_info[0]['status'] in [3, 4, -1, -2]:
            self.logger.info('%s-订单已经回调过 %s,确认成功' % (df_name, _order_info[0]['code']))
            return self.write('ok')  # 响应成功返回此结构

        if _order_info[0]['otherpay_id'] != id:
            if data['result'] == 'fail' and _order_info[0]['otherpay_id'] is None:  # 此三方会重复进行回调，已驳回的无法获取到三方支付ID
                self.logger.info('%s-订单已经回调过 %s,已成功驳回' % (df_name, _order_info[0]['code']))
                return self.write('ok')  # 响应成功返回此结构

            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info[0]['code']))

        if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['order_amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['order_no'],ret=_order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        _order_info = _order_info[0]
        # 查询订单确保回调安全
        data_post = dict()

        data_post['mer_no'] = mer_id
        data_post['order_no'] = _order_info['code']
        data_post['sign'] = SignatureAndVerification.sha256_sign(data_post, mer_key3, key_type='PKCS#8', is_url=False)
        data_post = json.dumps(data_post)
        self.logger.info('{df_name}-查询订单-发送地址{url},发送{data_post}'.format(df_name=df_name, url=r_t[0]['query_url'], data_post=data_post))
        # 超时重试
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                'Content-Type': 'application/json',
            }
            r = s.post(r_t[0]['query_url'], data=data_post, timeout=(30, 30), headers=headers, verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return await self.json_response({'success': False, 'message': 'error 查询第三方订单失败'})
        s.close()
        self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
        ret = json.loads(r.text)
        if not r.status_code == requests.codes.ok:
            # self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, data['clientNo'], r_t[0]['query_url'], r.status_code))
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
            return self.write('error 查询第三方订单失败')

        if str(ret["code"]) != '200':  # 接口响应中的状态码非成功
            self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["message"]))
            return self.write('error 响应码错误')

        if ret['data']['result_status'] not in ['success', 'fail', 'waiting']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        if not str(ret['data']['result_status']) == str(data['result']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(ret['data']['order_amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'status': "error", 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        if data['result'] in ['success']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("ok")

        if data['result'] in ['fail']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('ok')
class Quickpay(BaseHandler):
    async def post(self):
        """ 处理 quickpay 代付异步通知，并查询订单状态 """
        df_name = "quickpay"

        # 查询数据库，获取支付通道的配置信息
        sql_t = 'SELECT id, mer_id, mer_key, pay_name_zh, notify_ip, query_url, mer_key2, mer_key3 FROM third_pay_df WHERE pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key3 = r_t[0]['mer_key3']
        mer_key2 = r_t[0]['mer_key2']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write("notify_ip error")

        try:
            # 解析 POST JSON 请求数据
            data = json.loads(self.request.body)  # 将请求体中的 JSON 数据解析为字典
            self.logger.info(f"{df_name} 收到回调参数: {data}, IP: {ip}")

            # 校验签名
            # original_sign = data.pop("sign", "")
            if not SignatureAndVerification.verify_rsasha1_sign(mer_key2, data, data["sign"]):
                self.logger.error(f"{df_name} 签名错误: 接收到的签名 {data["sign"]}, ip: {ip}")
                return self.write('sign error')
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["orderId"])

        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['orderId']}")
            return self.write("error: no order")
        
        if not decimal.Decimal(order_info[0]['amount']) == decimal.Decimal(data['payment']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['orderId'],ret=order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        order_info = order_info[0]
        self.logger.info(f'order_info====={order_info}')

        # 防止重复处理
        if order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['orderId']}")
            return self.write("SUCCESS")

        if not order_info['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, data['serial_number']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, data['serial_number']))

        # 调用代付查询接口，检查订单支付状态
        query_data = {
            "merchantNo": mer_id,
            "payoutNo": data["payoutNo"],
            "orderId": data["orderId"]
        }
        query_data['sign'] = SignatureAndVerification.rsa_sha1_sign(query_data, mer_key3)  # 使用私钥生成
        query_data = json.dumps(query_data)  # 转换为 JSON 字符串
        self.logger.info(f"query_url={data['orderId']}==地址=={query_url}")
        self.logger.info(f"query_data=={data['orderId']}==参数=={query_data}")
        query_response = await self.query_order_status(query_url, query_data)
        self.logger.info(f"query_response={data['orderId']}==返回数据=={query_response}")
        
        if query_response["errNo"] != "0":
            self.logger.error(f"{df_name}-查询失败: {query_response['errStr']}")
            return self.write("query error")

        # 查询结果
        payout_status = query_response["data"]["status"]
        payout_status = str(payout_status)
        status = str(data['status'])
        self.logger.info(f"payout_status={payout_status}==data['status']=={data['status']}")
        if payout_status != data['status']:
            self.logger.error(f"{df_name}-状态不一致: {payout_status} / {status}")
            return self.write("query error")
        
        if payout_status == "2":
            # 支付成功
            self.logger.info(f"{df_name}-支付成功: {data['orderId']}")
            # 在此处更新订单状态为支付成功
            if not await success_third_df(self, order_info, utr=data['utr']):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=order_info['code']))
                return self.write('confirm error')
            return self.write("SUCCESS")
    
        elif payout_status == "3":
            # 支付失败
            self.logger.info(f"{df_name}-支付失败: {data['orderId']}")
            # 在此处更新订单状态为支付失败
            if not await cancel_third_df(self, order_info):
                return self.write('cancel error')
            return self.write('FAILED')
        else:
            # 支付中或其他状态
            self.logger.info(f"{df_name}-支付中: {data['orderId']}")
            return self.write("WAIT")

    async def query_order_status(self, query_url, query_data):
        """ 查询代付订单状态 """
        try:
            headers = {
                "Content-Type": "application/json"
            }

            # 向查询接口发送POST请求
            response = requests.post(query_url, data=query_data, headers=headers, timeout=(5, 10))

            # 打印返回的响应内容
            self.logger.info(f"QuickPay Transfer 订单-返回结果 {response.text}")

            # 解析JSON返回结果
            ret = response.json()

            # 打印解析后的返回结果
            self.logger.info(f"返回的数据类型: {type(ret)}")
            self.logger.info(f"返回结果: {ret}")
            
            return ret
        
        except requests.exceptions.RequestException as e:
            # 捕获所有requests相关的异常
            self.logger.error(f"查询代付订单失败: {e}")
            return {"errNo": "1", "errStr": str(e)}


class SnakePay(BaseHandler):
    async def post(self):
        """ 处理 snakepay 代付异步通知，并查询订单状态 """
        df_name = "snakepay"

        # 查询数据库，获取支付通道的配置信息
        sql_t = 'SELECT id, mer_id, mer_key, pay_name_zh, notify_ip, query_url, mer_key2, mer_key3 FROM third_pay_df WHERE pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write("notify_ip error")

        try:
            # 解析 POST JSON 请求数据
            data = json.loads(self.request.body)  # 将请求体中的 JSON 数据解析为字典
            self.logger.info(f"{df_name} 收到回调参数: {data}, IP: {ip}")

        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["orderNo"])

        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['orderNo']}")
            return self.write("error: no order")

        if not decimal.Decimal(order_info[0]['amount']) == decimal.Decimal(data['amount']):
            # self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['clientNo'], ret=_order_info[0]['amount']))
            self.logger.error(
                '错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=data['orderNo'],
                                                                                  ret=order_info[0]['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        order_info = order_info[0]
        self.logger.info(f'order_info====={order_info}')

        # 防止重复处理
        if order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['orderNo']}")
            return self.write("ok")

        if not order_info['otherpay_id'] == id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, id))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, id))

        if not str(mer_id) == str(data['merchantNo']):
            return self.write('merchantno error')
        # 无查询代付订单状态的接口，比对金额和商户后直接根据状态回调
        status = str(data['status'])
        # 1成功, 2失败, 3反转
        if status == "1":
            # 支付成功
            self.logger.info(f"{df_name}-支付成功: {data['orderNo']}")
            # 在此处更新订单状态为支付成功
            if not await success_third_df(self, order_info):
                self.logger.error(
                    '{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=order_info['code']))
                return self.write('confirm error')
            return self.write("ok")

        elif status == "2":
            # 支付失败
            self.logger.info(f"{df_name}-支付失败: {data['orderNo']}")
            # 在此处更新订单状态为支付失败
            if not await cancel_third_df(self, order_info):
                return self.write('cancel error')
            return self.write('ok')
        else:
            # 支付中或其他状态
            self.logger.info(f"{df_name}-支付中: {data['orderNo']}")
            return self.write("WAIT")

class Hkpay(BaseHandler):
    async def post(self):
        """ 处理 hkpay 代付异步通知，并查询订单状态 """
        df_name = "hkpay"

        # 查询数据库，获取支付通道的配置信息
        sql_t = 'SELECT id, mer_id, mer_key, pay_name_zh, notify_ip, query_url, mer_key2 FROM third_pay_df WHERE pay_name = %s'
        r_t = await self.query(sql_t, df_name)

        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key2 = r_t[0]['mer_key']  # MD5 签名密钥
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write("notify_ip error")

        try:
            # 解析 POST JSON 请求数据
            data = json.loads(self.request.body)
            self.logger.info(f"{df_name} 收到回调参数: {data}, IP: {ip}")

            # 校验签名
            original_sign = data.pop("sign", "")
            generated_sign = self.generate_md5_sign(data, mer_key2)

            if generated_sign != original_sign:
                self.logger.error(f"{df_name} 签名错误: 计算签名 {generated_sign}, 接收签名 {original_sign}")
                return self.write("sign error")
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["merchant_orderno"])

        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['merchant_orderno']}")
            return self.write("error: no order")

        if decimal.Decimal(order_info[0]['amount']) != decimal.Decimal(data['amount']):
            self.logger.error(f"{df_name}-金额不一致: 订单金额 {order_info[0]['amount']} != 回调金额 {data['amount']}")
            return self.write("error: amount mismatch")

        order_info = order_info[0]
        trade_result = str(data['status'])
        # **新加：查询订单，确保回调数据的正确性**
        query_status = await self.query_order_status(mer_id, mer_key2, data["merchant_orderno"], query_url)
        # 查询结果
        query_status = query_status['data']["status"]
        query_status = str(query_status)
        self.logger.error(f"{df_name}-查询订单返回值-{query_status}")
        self.logger.error(f"{df_name}-通知返回返回值-{trade_result}")
        if query_status is None:
            return self.write("error: query failed")
        if query_status != str(trade_result):
            self.logger.error(f"{df_name}-错误: 回调状态 {trade_result} 与查询状态 {query_status} 不一致")
            return self.write("error: status mismatch")

        # 防止重复处理
        if order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['merchant_orderno']}")
            return self.write("success")

        if order_info['otherpay_id'] != id:
            self.logger.error(f"{df_name}-错误: otherpay_id 不匹配 {data['merchantid']}")
            return self.write("otherpay_id mismatch")

        # 处理订单状态
        if str(data["status"]) == "success":
            self.logger.info(f"{df_name}-支付成功: {data['merchant_orderno']}")
            if not await success_third_df(self, order_info):
                self.logger.error(f"{df_name}-订单 {order_info['code']} 状态更新失败")
                return self.write("update error")
            return self.write("success")

        elif str(data["status"]) == "fail":
            self.logger.info(f"{df_name}-支付失败: {data['merchant_orderno']}")
            if not await cancel_third_df(self, order_info):
                return self.write("update error")
            return self.write("fail")

        return self.write("waiting")

    async def query_order_status(self, mer_id, mer_key, merchant_orderno, query_url):
        """ 查询代付订单状态 """
        query_data = {
            "merchantid": mer_id,
            "merchant_orderno": merchant_orderno,
            "type": "pay"
        }
        query_data["sign"] = self.generate_md5_sign(query_data, mer_key)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = requests.post(query_url, data=query_data, headers=headers, timeout=10)
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"查询代付订单失败: {e}")
            return {"code": 400, "errmsg": str(e), "data": {}}

    def generate_md5_sign(self, params, secret_key):
        """ 生成 MD5 签名 """
        sorted_items = sorted((k, str(v).strip()) for k, v in params.items() if v and k != "sign")
        sign_string = "&".join(f"{k}={v}" for k, v in sorted_items) + f"&key={secret_key}"
        return hashlib.md5(sign_string.encode("utf-8")).hexdigest().lower()

#Skpay代付异步通知
class SkPay(BaseHandler):
    async def post(self):
        df_name = "skpay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url,mer_key3 from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)
        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        mer_key3 = r_t[0]['mer_key3']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")
        
        try:
            data = json.loads(self.request.body)
            self.logger.info(f'[{df_name}] 收到回调参数: {data}, 来自 IP: {ip}')
            
            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data), ip=ip))
            # 验证签名
            headers = self.request.headers
            sign = headers.get('sign')
            method = 'POST'
            accesskey = headers.get('accesskey')
            timstamp = headers.get('timestamp')
            nonce = headers.get('nonce')
            url_path = '/api/df_notice/skpay'
            self.logger.info(f'[{df_name}] 收到回调参数headers: {headers}, 来自 IP: {ip}')
            raw_string = f"{method}&{url_path}&{accesskey}&{timstamp}&{nonce}"
            self.logger.info(f"[{df_name}] raw_string: {raw_string}")
            if not SignatureAndVerification.verify_signature_skpay(raw_string, mer_key3, sign):
                self.logger.error(f"[{df_name}] {data}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[{df_name}]  收到回调参数: {data}, 签名通过')
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")
        
        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay, otherpay_code FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["merchantOrderNo"])
        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['merchantOrderNo']}")
            return self.write("error: no order")
        if decimal.Decimal(order_info[0]['amount']) != decimal.Decimal(data['amount']):
            self.logger.error(f"{df_name}-金额不一致: 订单金额 {order_info[0]['amount']} != 回调金额 {data['amount']}")
            return self.write("error: amount mismatch")
        if data['status'] not in ['created', 'waiting', 'paying', 'success', 'failure', 'overrule']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')
        _order_info = order_info[0]
        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['merchantOrderNo']}")
            return self.write("success")

        if _order_info['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['merchant_order_id'],ret=_order_info['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        # 查询订单确保回调安全
        data_post = dict()

        # 商户订单号与平台订单号择一即可，两者均传入时需为同一张订单
        data_post['orderNo'] = _order_info["otherpay_code"] # 第三方订单号
        data_post['merchantOrderNo'] = _order_info['code'] # 商户订单号
        query_result = ''
        try:
            # 计算验证签名
            url_path = urlparse(r_t[0]['query_url']).path
            signature_info = SignatureAndVerification.generate_signature_skpay("POST", url_path, mer_key, mer_key3)
            # 构造请求头 ， 查询订单
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                "Content-Type": "application/json",
                "accessKey": r_t[0]['mer_key'],
                "timestamp": signature_info["timestamp"],
                "nonce": signature_info["nonce"],
                "sign": signature_info["sign"]
            }
            data_post = json.dumps(data_post)
            self.logger.info(f'query_url=============================={query_url}')
            r = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            ret = json.loads(r.text)
            self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            
            if not r.status_code == requests.codes.ok:
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
                return self.write('error 查询第三方订单失败')

            if str(ret["code"]) != '200000':  # 接口响应中的状态码非成功
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["message"]))
                return self.write('error 响应码错误')
            query_result = str(ret['data']['status'])
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return self.write('error 查询第三方订单失败')
        
        if str(data['status']) not in ['created', 'waiting', 'paying', 'success', 'failure', 'overrule']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 回调结果状态非法')
        
        if not query_result == str(data['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')

        if str(data['status']) in ['success']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("success")

        if str(data['status']) in ['failure', 'overrule']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')

        return self.write("waiting")


#catspay代付异步通知
class CatsPay(BaseHandler):
    async def get(self):
        df_name = "catspay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url,mer_key3 from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)
        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")

        try:
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info(f'[{df_name}] 收到回调参数: {data}, 来自 IP: {ip}')

            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data), ip=ip))
            # 验证签名
            signature = data['sign']
            sign_keys = ['merchant_id', 'merchant_orderid', 'merchant_para', 'money', 'orderid', 'status']
            sign_str = '&'.join('{}={}'.format(key, data[key]) for key in sign_keys) + mer_key
            expect_sign = SignatureAndVerification.get_md5_str(sign_str)
            if signature != expect_sign:
                self.logger.error(f"[{df_name}] {data}签名错误: 接收到的签名 {signature}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[{df_name}]  收到回调参数: {data}, 签名通过')
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay, otherpay_code FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["merchant_orderid"])
        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['merchant_orderid']}")
            return self.write("error: no order")
        if data['status'] not in ['1', '2']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')
        _order_info = order_info[0]
        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['merchant_orderid']}")
            return self.write("SUCCESS")

        if _order_info['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['money']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['merchant_order_id'],ret=_order_info['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        # 查询订单确保回调安全
        data_post = dict()

        # 商户订单号与平台订单号择一即可，两者均传入时需为同一张订单
        data_post['merchant_id'] = mer_id
        data_post['merchant_orderid'] = _order_info['code']
        data_post['datetime'] = display_now().strftime('%Y-%m-%d %H:%M:%S')
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, mer_key, 'catspay')
        try:
            # 构造请求头 ， 查询订单
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                "Content-Type": "application/x-www-form-urlencoded",
            }
            self.logger.info(f'query_url=============================={query_url}')
            r = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            ret = json.loads(r.text)
            self.logger.error('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))

            if not r.status_code == requests.codes.ok:
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
                return self.write('error 查询第三方订单失败')

            if str(ret["status"]) != '1':  # 接口响应中的状态码非成功
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["message"]))
                return self.write('error 响应码错误')
            query_status = str(ret['data']['status'])
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return self.write('error 查询第三方订单失败')

        if str(data['status']) not in ['1', '2']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 回调结果状态非法')

        if not query_status == str(data['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')

        if str(data['status']) in ['1']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("SUCCESS")

        if str(data['status']) in ['2']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('SUCCESS')

        return self.write("waiting")


#LemonPay3代付异步通知
class LemonPay3(BaseHandler):
    async def post(self):
        return await self.handle_notify()

    async def get(self):
        return await self.handle_notify()

    async def handle_notify(self):
        df_name = "lemonpay3"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url,mer_key3 from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)
        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        mer_key3 = r_t[0]['mer_key3']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")

        try:
            # data = json.loads(self.request.body)
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info(f'[{df_name}] 收到回调参数: {data}, 来自 IP: {ip}')

            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data), ip=ip))
            # 验证签名
            sign = data.pop('sign')
            if not SignatureAndVerification.md5_verify(data, sign, mer_key):
                self.logger.error(f"[{df_name}] {data}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[{df_name}]  收到回调参数: {data}, 签名通过')
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay, otherpay_code FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["mchOrderNo"])
        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['mchOrderNo']}")
            return self.write("error: no order")
        # 0-待处理,1-处理中,2-成功,3-失败,6-冲正
        if str(data['status']) not in ['0', '1', '2', '3', '6']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')
        _order_info = order_info[0]
        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['mchOrderNo']}")
            return self.write("success")

        if _order_info['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))

        if not decimal.Decimal(decimal.Decimal(_order_info['amount']) * 100) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name,code=data['merchant_order_id'],ret=_order_info['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        # 查询订单确保回调安全
        data_post = dict()

        # 商户订单号与平台订单号择一即可，两者均传入时需为同一张订单
        data_post['mchId'] = mer_id
        data_post['mchOrderNo'] = _order_info['code']
        data_post['reqTime'] = time.strftime("%Y%m%d%H%M%S")
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, mer_key)
        try:
            # 构造请求头 ， 查询订单
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                "Content-Type": "application/x-www-form-urlencoded",
            }
            self.logger.info(f'query_url=============================={query_url}')
            r = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            ret = json.loads(r.text)
            self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))

            if not r.status_code == requests.codes.ok:
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
                return self.write('error 查询第三方订单失败')

            if str(ret["retCode"]) != 'SUCCESS':  # 接口响应中的状态码非成功
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["message"]))
                return self.write('error 响应码错误')
            query_result = str(ret['status'])
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return self.write('error 查询第三方订单失败')

        if str(data['status']) not in ['0', '1', '2', '3', '6']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 回调结果状态非法')

        if not query_result == str(data['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')

        if str(data['status']) in ['2']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("success")

        if str(data['status']) in ['3', '6']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')

        return self.write("waiting")


class Pay188Pay(BaseHandler):
    """188pay代付异步通知"""
    async def post(self):
        df_name = "188pay"
        sql_t = 'select id,mer_id,mer_key,pay_name_zh,notify_ip,query_url,mer_key3 from third_pay_df where pay_name = %s'
        r_t = await self.query(sql_t, df_name)
        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        mer_key3 = r_t[0]['mer_key3']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")

        try:
            # data = json.loads(self.request.body)
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.logger.info(f'[{df_name}] 收到回调参数: {data}, 来自 IP: {ip}')

            self.logger.info('{df_name} data_receive-收到回调参数{data},{ip}'.format(df_name=df_name, data=str(data), ip=ip))
            # 验证签名
            sign = data.pop('sign')
            sign = sign.upper()
            if not SignatureAndVerification.md5_verify(data, sign, mer_key, key_name='secretKey'):
                self.logger.error(f"[{df_name}] {data}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[{df_name}]  收到回调参数: {data}, 签名通过')
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay, otherpay_code FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["orderId"])
        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {data['orderId']}")
            return self.write("error: no order")
        # 已受理: 0 成功: 1 失败: 2
        if str(data['status']) not in ['0', '1', '2']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')
        _order_info = order_info[0]
        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['orderId']}")
            return self.write("success")

        if _order_info['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        # 查询订单确保回调安全
        data_post = dict()

        # 商户订单号与平台订单号择一即可，两者均传入时需为同一张订单
        data_post['merchno'] = mer_id
        data_post['orderId'] = _order_info['code']
        data_post['timestamp'] = time.strftime("%Y%m%d%H%M%S")
        data_post['apiVersion'] = '2'
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, mer_key, key_name='secretKey').lower()
        try:
            # 构造请求头 ， 查询订单
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                "Content-Type": "application/x-www-form-urlencoded",
            }
            self.logger.info(f'query_url=============================={query_url}')
            r = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            ret = json.loads(r.text)
            self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))

            if not r.status_code == requests.codes.ok:
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
                return self.write('error 查询第三方订单失败')
            ret = ret.get('responseContent', {})

            if str(ret["code"]) != '0':  # 接口响应中的状态码非成功
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["message"]))
                return self.write('error 响应码错误')
            query_result = str(ret['status'])
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return self.write('error 查询第三方订单失败')

        if str(data['status']) not in ['0', '1', '2']:  # 失败
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 回调结果状态非法')

        if not query_result == str(data['status']):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')

        if str(data['status']) in ['1']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("success")

        if str(data['status']) in ['2']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('success')

        return self.write("waiting")
# TataPay代付异步通知
class TataPay(BaseHandler):
    async def post(self):
        payload = json.loads(self.request.body)
        data = payload.get("data", None)
        if not data or not data.get('merchNo', None):
            self.write(f"[{data}] request data error")

        df_name = "TataPay"
        sql_t = 'select id, mer_id, mer_key, pay_name_zh, notify_ip, query_url from third_pay_df where pay_name = %s and mer_id = %s'
        r_t = await self.query(sql_t, df_name, data.get('merchNo'))
        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        md5_key = r_t[0]['mer_key']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")

        try:
            self.logger.info(f"[{df_name}] 收到回调参数: {payload}, 来自 IP: {ip}")
            if payload.get("code") != 0:
                self.logger.error(f"{df_name}-错误: 回调状态码不是成功: {payload}")
                return self.write("error: invalid status code")

            sign = data.pop("sign", "")
            sorted_items = sorted(data.items())
            source = '&'.join(f"{k}={v}" for k, v in sorted_items)
            raw_sign = hashlib.md5((source + md5_key).encode()).hexdigest()

            if sign != raw_sign:
                self.logger.error(f"{df_name}-错误: 签名验证失败，计算值 {raw_sign}, 实际值 {sign}")
                return self.write("sign error")

            self.logger.info(f"[{df_name}] 签名验证通过")

        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        order_no = str(data.get("orderNo"))
        amount = data.get("amount")
        order_state = str(data.get("orderState"))
        businessNo = str(data.get("businessNo"))

        if businessNo in ["0", "1", "2", "3", "4", "5"]:
            self.logger.info(f'{df_name}not success or not fail: {order_no}')
            return self.write('not success or not fail')

        # 保存utr
        # if businessNo:
        #     sql = "UPDATE orders_df SET utr=%s WHERE code=%s"
        #     await self.execute(sql, businessNo, order_no)
        #     self.logger.info(f'[{df_name}] Transfer 订单-{order_no}-更新成功, utr-{businessNo}')

        # 查询订单
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay_code, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, order_no)
        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {order_no}")
            return self.write("error: no order")
        _order_info = order_info[0]

        if _order_info['otherpay_id'] != id:
            self.logger.error(f"{df_name}-{_order_info['code']} 错误：otherpay_id不符")
            return self.write(f"{df_name}-{_order_info['code']} 错误：otherpay_id不符合")

        if decimal.Decimal(_order_info['amount']) != decimal.Decimal(amount):
            self.logger.error(f"{df_name}-金额不一致: 订单金额 {_order_info['amount']} != 回调金额 {amount}")
            return self.write("error: amount mismatch")

        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {_order_info['code']}")
            return self.write("ok")

        # 发起查询请求验证
        query_payload = {
            "orderNo": _order_info['code'],
            "merchNo": mer_id
        }
        sorted_query = sorted(query_payload.items())
        query_string = '&'.join(f"{k}={v}" for k, v in sorted_query)
        query_sign = hashlib.md5((query_string + md5_key).encode()).hexdigest()
        query_payload["sign"] = query_sign

        try:
            resp = requests.post(query_url, json=query_payload, timeout=(5, 5), verify=False)
            self.logger.info(f"[{df_name}] 查询订单返回: {resp.text}")
            if resp.status_code != 200:
                return self.write("error 查询失败")
            ret = resp.json()
            self.logger.info(f"[{df_name}] 查询订单返回orderState: {ret["data"]["orderState"]}")
            if str(ret.get("code")) != "0":
                return self.write("error 查询状态码错误")
            if str(ret["data"]["orderState"]) != order_state:
                return self.write("error 状态不一致")
        except Exception as e:
            self.logger.error(f"{df_name}-查询接口异常: {e}")
            return self.write("error: query exception")

        if order_state == "1":  # 成功
            if not await success_third_df(self, _order_info, utr=businessNo):
                return self.write("confirm error")
            return self.write("ok")
        elif order_state in ["2", "4", "5"]:  # 失败/关闭/退回
            if not await cancel_third_df(self, _order_info):
                return self.write("cancel error")
            return self.write("ok")
        else:
            self.logger.info(f"{df_name}-状态处理中或未知: {order_state}")
            return self.write("ok")

class OsPay(BaseHandler):
    """ospay代付异步通知"""
    async def post(self):
        data = dict(parse.parse_qsl(self.request.body.decode()))

        # 查询数据库，确保订单存在
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay, otherpay_code FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, data["order_id"])
        if not order_info:
            self.logger.error(f"OSPAY-错误: 订单不存在 {data['order_id']}")
            return self.write("error: no order")
        _order_info = order_info[0]
        sql_t = 'select id,mer_id,mer_key,pay_name,pay_name_zh,notify_ip,query_url,mer_key3 from third_pay_df where id = %s'
        r_t = await self.query(sql_t, _order_info['otherpay_id'])
        if not r_t:
            self.logger.error(f"OSPAY-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        df_name = r_t[0]['pay_name']
        # 获取商户配置信息
        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        mer_key = r_t[0]['mer_key']
        mer_key3 = r_t[0]['mer_key3']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        # 校验回调来源 IP
        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")

        try:
            self.logger.info(f'[{df_name}] 收到回调参数: {data}, 来自 IP: {ip}')
            # 验证签名
            sign = data.pop('sign')
            self.logger.info(f'{sign}')
            sign = sign.upper()
            if not SignatureAndVerification.md5_verify(data, sign, mer_key):
                self.logger.error(f"[{df_name}] {data}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[{df_name}]  收到回调参数: {data}, 签名通过')
        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")
        # ok为订单代付成功； error为代付失败，订单取消
        if str(data['status']) not in ['ok', 'error']:
            self.logger.info('not success or not fail')
            return self.write('not success or not fail')
        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {data['order_id']}")
            return self.write("ok")

        if _order_info['otherpay_id'] != id:
            self.logger.error('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))
            return self.write('%s-%s 错误：otherpay_id不符合' % (df_name, _order_info['code']))

        if not decimal.Decimal(_order_info['amount']) == decimal.Decimal(data['amount']):
            self.logger.error('错误：{df_name}-查询订单{code},金额不一致，订单金额为{ret}'.format(df_name=df_name, code=_order_info['code'], ret=_order_info['amount']))
            return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        # 查询订单确保回调安全
        data_post = dict()
        # 商户订单号与平台订单号择一即可，两者均传入时需为同一张订单
        data_post['mer_id'] = mer_id
        data_post['order_id'] = _order_info['code']
        data_post["sign"] = SignatureAndVerification.md5_sign(data_post, mer_key)
        try:
            # 构造请求头 ， 查询订单
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                "Content-Type": "application/x-www-form-urlencoded",
            }
            self.logger.info(f'query_url=============================={query_url}')
            r = requests.post(query_url, params=data_post, headers=headers, timeout=(5, 5), verify=False)
            ret = json.loads(r.text)
            self.logger.info('{df_name}-查询订单{code},结果{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))

            if not r.status_code == requests.codes.ok:
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % (df_name, _order_info['code'], r_t[0]['query_url'], r.status_code))
                return self.write('error 查询第三方订单失败')

            if str(ret["code"]) != '0':  # 接口响应中的状态码非成功
                self.logger.error('%s-查询订单%s,接口错误 %s %s' % ( df_name, _order_info['code'], r_t[0]['query_url'], ret["message"]))
                return self.write('error 响应码错误')
            query_result = str(ret['data']['status'])
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (df_name, _order_info['code'], r_t[0]['query_url'], e))
            return self.write('error 查询第三方订单失败')

        if not ((data['status'] == 'ok' and query_result == '0') or (data['status'] == 'error' and query_result == '2')):
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致')

        if str(data['status']) in ['ok']:  # 成功
            if not await success_third_df(self, _order_info):
                self.logger.error('{df_name}-订单{code},success_third_df 失败'.format(df_name=df_name, code=_order_info['code']))
                return self.write('confirm error')
            return self.write("ok")

        if str(data['status']) in ['error']:  # 失败
            if not await cancel_third_df(self, _order_info):
                return self.write('cancel error')
            return self.write('ok')

        return self.write("waiting")

class VibraPay(BaseHandler):
    async def post(self):
        df_name = "VibraPay"
        form_data = dict(parse.parse_qsl(self.request.body.decode()))
        mer_id = form_data.get("merchant")
        sql_third_pay_df = 'select id,mer_id,mer_key,pay_name,pay_name_zh,notify_ip,query_url,mer_key2 from third_pay_df where mer_id = %s'
        third_pay_dfs = await self.query(sql_third_pay_df, mer_id)
        if not third_pay_dfs:
            self.logger.error(f"[{df_name}]-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")
        third_pay_df = third_pay_dfs[0]
        notify_ips = third_pay_df['notify_ip'].split(",") if third_pay_df['notify_ip'] else []

        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"[{df_name}]-警告: 非法回调 IP {ip}")
            return self.write(f"error notify_ip")
        
        self.logger.info(f"[{df_name}] 收到回调参数: {form_data}, 来自 IP: {ip}")
        if str(form_data.get("code")) != '0':
            self.logger.error(f"[{df_name}]-错误: 回调状态码不是成功: {form_data}")
            return self.write("error: invalid status code")
        try:
            encrypted_order = form_data.get("order", "")
            encrypted_order = encrypted_order.encode('utf-8').decode('unicode_escape') #还原\\n
            decrypted_order = SignatureAndVerification.aes_256_cbc_decrypt(third_pay_df['mer_key'], third_pay_df['mer_key2'], encrypted_order)
            order_callback = json.loads(decrypted_order)
        except Exception as e:
            self.logger.exception(f"[{df_name}]-异常: 解密订单信息失败: {e}")
            return self.write("error: invalid data")
        
        self.logger.info(f"[{df_name}] 解密的订单信息: {order_callback}")

        if order_callback.get("status") in ['success_done', 'fail_done']:
            self.logger.info(f"[{df_name}]: 忽略处理success_done/fail_done状态回调")
            return self.write('ok')
        if order_callback.get("status") not in ['success', 'fail']:
            self.logger.info(f"[{df_name}]: not success or not fail")
            return self.write('not success or not fail')
        
        order_code = form_data.get("merchant_order_num")
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay, otherpay_code FROM orders_df WHERE code = %s'
        order_infos = await self.query(sql_order, order_code)
        if not order_infos:
            self.logger.error(f"[{df_name}]-错误: 订单不存在 {order_code}")
            return self.write("error: no order")
        order_info = order_infos[0]

        if order_info['otherpay_id'] != third_pay_df['id']:
            self.logger.error(f"[{df_name}]-错误: 订单{order_info['code']} otherpay_id不符")
            return self.write(f"error: otherpay_id not match")

        try:
            order_info_amount = decimal.Decimal(order_info['amount'])
            form_data_amount = decimal.Decimal(order_callback.get("amount"))
        except decimal.InvalidOperation:
            self.logger.error(f"[{df_name}]-错误: 订单{order_info['code']} 金额格式错误: 订单金额 {order_info['amount']} 回调金额 {form_data.get('amount')}")
            return self.write("error: invalid amount format")

        if order_info_amount != form_data_amount:
            self.logger.error(f"[{df_name}]-错误: 订单{order_info['code']} 金额不一致: 订单金额 {order_info['amount']} != 回调金额 {form_data.get('amount')}")
            return self.write("error: amount mismatch")

        if order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"[{df_name}]: 订单{order_info['code']} 已处理过")
            return self.write("ok")

        query_params = {
            "merchant_order_num": order_info['code']
        }
        encrypted_query_params = SignatureAndVerification.aes_256_cbc_encrypt(third_pay_df['mer_key'], third_pay_df['mer_key2'], json.dumps(query_params))
        data_post = {
            "merchant_slug": mer_id,
            "data": encrypted_query_params
        }

        try:
            resp = requests.post(third_pay_df['query_url'], json=data_post, timeout=(5, 5), verify=False)
            self.logger.info(f"[{df_name}]: 查询订单返回: {resp.text}")
            if resp.status_code != 200:
                return self.write("error 查询失败")
            ret = resp.json()
        except Exception as e:
            self.logger.error(f"[{df_name}]-错误: 查询接口异常: {e}")
            return self.write("error: query exception")

        if str(ret.get("code")) != "0":
            return self.write("error 查询状态码错误")

        decrypted_order = SignatureAndVerification.aes_256_cbc_decrypt(third_pay_df['mer_key'], third_pay_df['mer_key2'], ret.get('order'))
        query_order = json.loads(decrypted_order)
        self.logger.info(f"[{df_name}]: 查询订单-解密后的订单信息: {query_order}")
        if query_order['status'] != order_callback['status']:
            return self.write("error 状态不一致")

        if order_callback['status'] == "success":  # 成功
            if not await success_third_df(self, order_info):
                return self.write("confirm error")
            return self.write("ok")
        elif order_callback['status'] in ["fail", "reverted"]:  # 失败/关闭/退回
            if not await cancel_third_df(self, order_info):
                return self.write("cancel error")
            return self.write("ok")
        else:
            self.logger.info(f"[{df_name}]: 状态为处理中或未知: {order_callback['status']}")
            return self.write("ok")

# qqpay代付异步通知
class qqpay(BaseHandler):
    async def post(self):
        payload = json.loads(self.request.body)
        data = payload.get("data", None)
        df_name = "qqpay"
        sql_t = 'select id, mer_id, mer_key, pay_name_zh, notify_ip, query_url from third_pay_df where pay_name = %s and mer_id = %s'
        r_t = await self.query(sql_t, df_name, data.get('merchant_id'))
        if not r_t:
            self.logger.error(f"{df_name}-错误: 获取支付通道配置信息失败")
            return self.write("error: no config")

        id = r_t[0]['id']
        mer_id = r_t[0]['mer_id']
        md5_key = r_t[0]['mer_key']
        notify_ips = r_t[0]['notify_ip'].split(",") if r_t[0]['notify_ip'] else []
        query_url = r_t[0]['query_url']

        ip = await self.get_ip()
        if ip not in notify_ips:
            self.logger.warning(f"{df_name}-警告: 非法回调 IP {ip}")
            return self.write(f"[{df_name}] notify_ip error")

        try:
            self.logger.info(f"[{df_name}] 收到回调参数: {payload}, 来自 IP: {ip}")
            if str(payload.get("code")).strip() not in ['200','201']:
                self.logger.error(f"{df_name}-错误: 回调状态码不是成功: {payload}")
                return self.write("error: invalid status code")

            sign = data.pop("sign", "")
            raw_sign = SignatureAndVerification.hmac_sha256_sign3(data, md5_key)
            if sign != raw_sign:
                self.logger.error(f"{df_name}-错误: 签名验证失败，计算值 {raw_sign}, 实际值 {sign}")
                return self.write("sign error")

            self.logger.info(f"[{df_name}] 签名验证通过")

        except Exception as e:
            self.logger.exception(f"{df_name}-错误: 解析回调参数失败: {e}")
            return self.write("error: invalid data")

        order_no = str(data.get("mer_order_num"))
        amount = data.get("price")
        businessNo = str(data.get("order_num"))
        utr = str(data.get("utr"))

        # 查询订单
        sql_order = 'SELECT code, amount, status, otherpay_id, otherpay_code, otherpay FROM orders_df WHERE code = %s'
        order_info = await self.query(sql_order, order_no)
        if not order_info:
            self.logger.error(f"{df_name}-错误: 订单不存在 {order_no}")
            return self.write("error: no order")
        _order_info = order_info[0]

        if _order_info['otherpay_id'] != id:
            self.logger.error(f"{df_name}-{_order_info['code']} 错误：otherpay_id不符")
            return self.write(f"{df_name}-{_order_info['code']} 错误：otherpay_id不符合")

        if decimal.Decimal(_order_info['amount']) != decimal.Decimal(amount):
            self.logger.error(f"{df_name}-金额不一致: 订单金额 {_order_info['amount']} != 回调金额 {amount}")
            return self.write("error: amount mismatch")

        if _order_info["status"] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单已处理过: {_order_info['code']}")
            return self.write("success")


        # 发起 POST 请求到查询接口
        data_post = dict()
        data_post['merchant_id'] = mer_id
        data_post['mer_order_num'] = order_no
        data_post['timestamp'] = str(int(time.time()))
        data_post['type'] = 2
        # 计算验证签名
        data_post['sign'] = SignatureAndVerification.hmac_sha256_sign3(data_post, md5_key)
        # 构造请求头 ， 查询订单
        headers = {
            "Content-Type": "application/json",
        }
        try:
            data_post = json.dumps(data_post)
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')
        except Exception as e:
            self.logger.error(f"{df_name}-查询接口异常: {e}")
            return self.write("error: query exception")

        if not str(result.get('code')) == '200':
            self.logger.error(f"查询错误: [{result.get('code')}]")
            return self.write(f"查询错误: {result.get('code')}")

        query_status = str(result.get("data", {}).get('status'))
        self.logger.info(f"[qqpay] 查询订单返回值: {query_status}")
        if query_status is None:
            return self.write("error: query failed")

        # 判断订单支付状态
        if query_status == "2":
            if not await success_third_df(self, _order_info, utr=utr):
                return self.write("confirm error")
            return self.write("success")
        elif query_status == "3":
            if not await cancel_third_df(self, _order_info):
                return self.write("cancel error")
            return self.write("success")
        else:
            self.logger.info(f"[{df_name}]: 状态为处理中或未知: {query_status}")
            return self.write("error")

# marspay代付异步通知
class marspay(BaseHandler):
    async def get(self):
        df_name = "marspay"
        # 从数据库查询支付通道配置信息
        sql_t = 'select id, mer_id, mer_key, notify_ip, query_url from third_pay_df where pay_name = %s and mer_id = %s'
        r_t = await self.query(sql_t, df_name, df_name)
        if not r_t or not r_t[0]['notify_ip']:
            self.logger.info(f"{df_name}-无回调通知ip或配置失败，请检查")
            return self.write("not notify_ip")

        # 检查回调 IP
        ip = await self.get_ip()
        notify_ips = r_t[0]['notify_ip'].split(",")
        if ip != '127.0.0.1' and ip not in notify_ips:
            self.logger.info(f"{df_name}-回调通知ip({ip})不在允许IP列表中:({notify_ips})")
            return self.write("notify_ip error")

        # 获取并解析回调参数
        try:
            # 遍历 request.arguments，并对键和值进行解码
            data_receive = {}
            for key, values in self.request.arguments.items():
                # key 已经是字符串，values 是一个包含字节字符串的列表
                decoded_value = values[0].decode('utf-8')
                data_receive[key] = decoded_value
            
            self.logger.info(f"{df_name} data_receive-收到回调参数 {data_receive}, 来自 IP: {ip}")
            data = data_receive
        except Exception as e:
            self.logger.exception(f"{df_name} 参数解析异常")
            return self.json_response({'status': 'error', 'message': 'invalid parameters'})

        # 检查必要参数
        if data.get('status', '').lower() not in ['success', 'failure', 'refund failure']:
            self.logger.info(f"{df_name}-订单状态为 {data.get('status', '')}，非终态")
            return self.write("not success or fail")

        # 防止生成订单即刻回调
        if ip != '127.0.0.1':
            self.logger.info(f"[{df_name}] 订单 {data['client_id']} 收到回调，等待 20 秒以防止即刻回调。")
            await asyncio.sleep(20)
            self.logger.info(f"[{df_name}] 订单 {data['client_id']} 等待 20 秒结束，继续处理回调。")

        # 查询订单信息
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df where code = %s'
        _order_info_list = await self.query(sql_order_info, data['client_id'])

        if not _order_info_list:
            self.logger.error(f'{df_name}-错误，无此订单 {data["client_id"]}')
            return self.json_response({'status': 'error', 'message': 'error 无此订单'})
        
        _order_info = _order_info_list[0]
        
        # 若订单已经成功了，则直接返回回调成功
        if _order_info['status'] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单 {_order_info['code']} 已经回调过，确认成功")
            return self.write("success")

        # 检查 otherpay_id
        config_id = r_t[0]['id']
        if _order_info['otherpay_id'] != config_id:
            self.logger.error(f"{df_name}-{_order_info['code']} 错误：otherpay_id不符合 {_order_info['otherpay_id']} != {config_id}")
            return self.write("error：otherpay_id不符合")

        # 查询第三方订单确保回调安全
        try:
            data_get = {'api_token': r_t[0]['mer_key'], 'client_id': data['client_id']}
            
            s = requests.Session()
            s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
            s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
            }
            r = s.get(r_t[0]['query_url'], params=data_get, timeout=(5, 10), headers=headers)
            r.raise_for_status()
            
            ret = json.loads(r.text)
            s.close()
        except requests.exceptions.RequestException as e:
            self.logger.error(f'{df_name}-查询订单 {data["client_id"]} 接口超时或错误: {e}')
            return self.write("error: query api failed")
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f'{df_name}-查询订单 {data["client_id"]} 响应数据解析失败: {r.text}, 异常: {e}')
            return self.write("error: invalid json")
        
        # 验证查询结果
        if not (ret.get("status") == "success" and ret.get("message") == "success"):
            self.logger.error(f'{df_name}-查询订单 {data["client_id"]} 接口响应失败: {ret}')
            return self.write('error: query status fail')
        
        query_data = ret.get("transaction", {})
        query_status = query_data.get("status", "").lower()
        query_amount_raw = query_data.get("amount", 0)

        # --- 关键修改部分开始 ---
        if isinstance(query_amount_raw, str):
            query_amount_cleaned = query_amount_raw.replace(',', '').replace(' ', '')
        else:
            query_amount_cleaned = query_amount_raw

        try:
            query_amount = decimal.Decimal(query_amount_cleaned)
        except decimal.InvalidOperation:
            self.logger.error(f"转换金额失败: {query_amount_raw}")
            query_amount = decimal.Decimal(0)
        # --- 关键修改部分结束 ---

        self.logger.info(f"[{df_name}] 查询结果解析: query_data={query_data}, query_status='{query_status}', query_amount='{query_amount}'")

        # 校验金额
        if not decimal.Decimal(str(_order_info['amount'])) == decimal.Decimal(str(query_amount)):
            self.logger.error(f"{df_name}-订单 {_order_info['code']} 金额不一致: 订单金额 {_order_info['amount']} != 查询金额 {query_amount}")
            return self.json_response({'success': False, 'message': 'error 金额不一致'})
        
        # marspay 的状态映射
        status_mapping = {
            'success': 'success',
            'failure': 'failed',
            'refund failure': 'failed',
        }

        # 校验回调状态与查询状态是否一致
        # 将外部状态映射为内部状态，再进行比较
        callback_status_norm = status_mapping.get(data['status'].lower(), 'unknown')
        query_status_norm = status_mapping.get(query_status, 'unknown')

        # sd pay state字段状态：
        # 订单状态 1:待支付, 2:成功, 3失败
        if callback_status_norm not in ['success', 'failed']:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致1，{ret}'.format(df_name=df_name,code=_order_info['code'],ret=r.text))
            return self.write('error 查询订单与回调结果不一致')
        # 校验回调状态与查询状态是否一致
        if callback_status_norm != query_status_norm:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        # 根据最终状态处理订单
        if query_status_norm == "success":
            if not await success_third_df(self, _order_info):
                self.logger.error(f"{df_name}-订单 {_order_info['code']}, success_third_df 失败")
                return self.write("confirm error")
            return self.write("success")
        elif query_status_norm == "failed":
            if not await cancel_third_df(self, _order_info):
                self.logger.error(f"{df_name}-订单 {_order_info['code']}, cancel_third_df 失败")
                return self.write("cancel error")
            return self.write("success")
        
        self.logger.info(f"[{df_name}]: 订单 {data['client_id']} 状态为处理中或未知: {query_status}")
        return self.write("processing")

# Gamepayer 代付异步通知
class gamepayer(BaseHandler):
    async def get(self):
        # 检查回调 IP
        ip = await self.get_ip()
        df_name = "gamepayer"
        # 获取并解析回调参数
        try:
            # 遍历 request.arguments，并对键和值进行解码
            data = {}
            for key, values in self.request.arguments.items():
                # key 已经是字符串，values 是一个包含字节字符串的列表
                decoded_value = values[0].decode('utf-8')
                data [key] = decoded_value

            self.logger.info(f"{df_name} data_receive-收到回调参数 {json.dumps(data)}, 来自 IP: {ip}")
        except Exception as e:
            self.logger.exception(f"{df_name} 参数解析异常")
            return self.json_response({'status': 'error', 'message': 'invalid parameters'})

        # 从数据库查询支付通道配置信息
        sql_t = 'select id, mer_id, mer_key, notify_ip, query_url from third_pay_df where pay_name = %s and mer_id = %s'
        r_t = await self.query(sql_t, df_name, data['merchant_id'])
        if not r_t or not r_t[0]['notify_ip']:
            self.logger.info(f"{df_name}-无回调通知ip或配置失败，请检查")
            return self.write("not notify_ip")

        notify_ips = r_t[0]['notify_ip'].split(",")
        if ip != '127.0.0.1' and ip not in notify_ips:
            self.logger.info(f"{df_name}-回调通知ip({ip})不在允许IP列表中:({notify_ips})")
            return self.write("notify_ip error")

        try:
            sign = data.pop('sign', None)
            sign_str = f'merchant_id={data.get('merchant_id','')}&merchant_orderid={data.get('merchant_orderid','')}&merchant_para={data.get('merchant_para','')}&money={data.get('money','')}&orderid={data.get('orderid','')}&status={data.get('status','')}{r_t[0]['mer_key']}'
            sign_str = SignatureAndVerification.get_md5_str(sign_str).lower()
            if sign != sign_str:
                self.logger.error(f"{df_name}-错误: 签名验证失败，计算值 {sign_str}, 实际值 {sign}")
                return self.write("sign error")
            self.logger.info(f"{df_name}-签名验证通过")
        except  Exception as e:
            self.logger.exception(f"{df_name}-错误: 签名失败: {e}")
            return self.write("error: sign fail")

        # 防止生成订单即刻回调
        if ip != '127.0.0.1':
            self.logger.info(f"[{df_name}] 订单 {data['merchant_orderid']} 收到回调，等待 20 秒以防止即刻回调。")
            await asyncio.sleep(20)
            self.logger.info(f"[{df_name}] 订单 {data['merchant_orderid']} 等待 20 秒结束，继续处理回调。")

        # 查询订单信息
        sql_order_info = 'select code, amount, status, otherpay_id, otherpay from orders_df where code = %s'
        _order_info_list = await self.query(sql_order_info, data['merchant_orderid'])

        if not _order_info_list:
            self.logger.error(f'{df_name}-错误，无此订单 {data["merchant_orderid"]}')
            return self.json_response({'status': 'error', 'message': 'error 无此订单'})

        _order_info = _order_info_list[0]
        # 若订单已经成功了，则直接返回回调成功
        if _order_info['status'] in [3, 4, -1, -2]:
            self.logger.info(f"{df_name}-订单 {_order_info['code']} 已经回调过，确认成功")
            return self.write("SUCCESS")

        # 检查 otherpay_id
        config_id = r_t[0]['id']
        if _order_info['otherpay_id'] != config_id:
            self.logger.error(f"{df_name}-{_order_info['code']} 错误：otherpay_id不符合 {_order_info['otherpay_id']} != {config_id}")
            return self.write("error：otherpay_id不符合")

        # 查询第三方订单确保回调安全
        try:
            data_get = {
                'merchant_id': r_t[0]['mer_id'],
                'merchant_orderid': _order_info['code'],
                "datetime": display_now().strftime('%Y-%m-%d %H:%M:%S')
            }
            data_get['sign'] = SignatureAndVerification.md5_sign(data_get, r_t[0]['mer_key'], "catspay")

            s = requests.Session()
            s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
            s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                              'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                              'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) '
                              'AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans '
                              'useStatusBar/true isConcaveScreen/false Region/CN',
            }
            r = s.post(r_t[0]['query_url'], data=data_get, timeout=(5, 10), headers=headers)
            r.raise_for_status()

            ret = json.loads(r.text)
            s.close()
        except requests.exceptions.RequestException as e:
            self.logger.error(f'{df_name}-查询订单 {data["merchant_id"]} 接口超时或错误: {e}')
            return self.write("error: query api failed")
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f'{df_name}-查询订单 {data['merchant_id']} 响应数据解析失败: {r.text}, 异常: {e}')
            return self.write("error: invalid json")

        # 验证查询结果
        if not ret.get("status", None) == "1":
            self.logger.error(f'{df_name}-查询订单 {data["merchant_id"]} 接口响应失败: {ret}')
            return self.write('error: query status fail')

        self.logger.info(f"[{df_name}] 查询结果解析: query_data={json.dumps(ret)}")

        query_data = ret.get("data", {})
        query_status = query_data.get("status", None)
        if data['status'] != query_status:
            self.logger.error('错误：{df_name}-查询订单{code},查询订单与回调结果不一致2，{ret}'.format(df_name=df_name, code=_order_info['code'], ret=r.text))
            return self.write('error 查询订单与回调结果不一致2')

        query_amount_raw = query_data.get("money", 0)
        # --- 关键修改部分开始 ---
        if isinstance(query_amount_raw, str):
            query_amount_cleaned = query_amount_raw.replace(',', '').replace(' ', '')
        else:
            query_amount_cleaned = query_amount_raw

        try:
            query_amount = decimal.Decimal(query_amount_cleaned)
        except decimal.InvalidOperation:
            self.logger.error(f"转换金额失败: {query_amount_raw}")
            query_amount = decimal.Decimal(0)
        # --- 关键修改部分结束 ---

        # 校验金额
        if not decimal.Decimal(str(_order_info['amount'])) == decimal.Decimal(str(query_amount)):
            self.logger.error(f"{df_name}-订单 {_order_info['code']} 金额不一致: 订单金额 {_order_info['amount']} != 查询金额 {query_amount}")
            return self.json_response({'success': False, 'message': 'error 金额不一致'})

        # 根据最终状态处理订单
        if query_status == "1":
            if not await success_third_df(self, _order_info):
                self.logger.error(f"{df_name}-订单 {_order_info['code']}, success_third_df 失败")
                return self.write("confirm error")
        else:
            if not await cancel_third_df(self, _order_info):
                self.logger.error(f"{df_name}-订单 {_order_info['code']}, cancel_third_df 失败")
                return self.write("cancel error")

        return self.write("SUCCESS")
