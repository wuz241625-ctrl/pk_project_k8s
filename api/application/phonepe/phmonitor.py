import json
import multiprocessing
import time
from decimal import Decimal
import re

import bcrypt
from aiomysql import DictCursor
from tornado import websocket
from tornado.ioloop import IOLoop

from application.app.websocket import app
from application.base import BaseHandler, RewriteJsonEncoder
from application.phonepe import callback
import hashlib

import traceback
import simplejson

phonepe_socket = {}


class Websocket(BaseHandler, websocket.WebSocketHandler):

    def check_origin(self, origin):
        return True

    def open(self):
        self.logger.info('ws connect')

    def on_close(self):
        self.logger.info('ws close')
        IOLoop.current().add_callback(self.clean)

    async def on_message(self, message):
        try:
            if message == 'pong':
                return await self.write_message('pong')
            # print(message)
            data = json.loads(message)
            if data['type'] == 'Login':
                await self.write_message(await self.login(data))
            # if data['type'] == 'Start':
            #     await self.start(data)
            # 20240913 该方法移除处理
            if data['type'] == 'Online':
                return await self.write_message(await self.qrcode_online(data['online']))
            if data['type'] == 'Offline':
                return await self.write_message(await self.logout())
            if data['type'] == 'UPI':
                upi = await self.get_result_by_condition('payment', ['upi'], {'id': self.payment_id})
                if not upi['upi'] or upi['upi'] != data['upi']:
                    if not await self.update_result('payment', {'upi': data['upi']}, {'id': self.payment_id}):
                        return dict(type='UPI', code=200, msg='update upi error.')
                return dict(type='UPI', code=200, msg='update upi success.')
            if data['type'] == 'New':
                return await self.write_message(await self.new_record(data))
        except Exception as e:
            self.logger.info(e)
            # 记录详细的错误信息
            error_info = {
                'line': e.__traceback__.tb_lineno,  # 错误发生的行号
                'file': e.__traceback__.tb_frame.f_code.co_filename,  # 错误发生的文件名
                'message': str(e)  # 错误的消息
            }
            self.logger.info(f"An error occurred: {str(e)}\nDetails: {error_info}")
            ret = dict(type='Error', code=99, msg='data error.')
            await self.write_message(json.dumps(ret))

    # 连接
    async def login(self, data):
        if await self.is_null(data, ['payment_id', 'password']):
            return dict(type='Login', code=99, msg='data error')
        self.payment_id = data['payment_id']
        keys = ['partner_id', 'status', 'certified', 'account_type', 'bank_type_id', 'channel','phone']
        payment = await self.get_result_by_condition('payment', keys, {'id': self.payment_id})
        if not payment or not payment['status'] or not payment['certified']:
            return dict(type='Login', code=99, msg='payment error')
        self.partner_id = payment['partner_id']
        keys = ['id', 'name']
        bank_type = await self.get_result_by_condition('bank_type', keys, {'id': payment['bank_type_id']})
        if not bank_type or not bank_type['name']:
            return dict(type='Login', code=99, msg='bank_type error')
        self.bank_type = bank_type['name']

        # 将所有通道存储到 self.qr_channels 列表中
        self.qr_channels = payment['channel'].split(',')  # 通道是以逗号分隔的字符串

        partner = await self.get_result_by_condition('partner', ['hash_login', 'status', 'certified'],
                                                     {'id': payment['partner_id']})
        if not bcrypt.checkpw(data['password'].encode('utf8'), partner['hash_login'].encode('utf8')):
            return dict(type='Login', code=99, msg='ID or PW Incorrect')
        # 后台锁定不要限制短信监控登入，保持卡商能一直登入 20250312
        # if not partner['status'] or not partner['certified']:
        #     return dict(type='Login', code=99, msg='partner error')

        # heartbeat_key = f'heartbeat:{self.payment_id}'  # 辅助key，维持心跳状态
        if payment['certified']:
            # 更新 Redis 数据
            await self.redis.sadd('payment_online_ds', self.payment_id)
            # 定义 Redis Key
            redis_key = 'payment_online_ds_phone'
            # 2. 查询手机号是否在采集状态列表
            existing_payments = await self.redis.get(redis_key)
            is_monitored = False

            if existing_payments:
                # 解析存储的字符串（按逗号分隔）
                # 如果 Redis 返回的是 bytes，则先解码
                if isinstance(existing_payments, bytes):
                    existing_payments = existing_payments.decode()

                # 解析存储的字符串（按逗号分隔）
                payment_list = existing_payments.split(',')
                is_monitored = self.payment_id in payment_list

            self.logger.info(f"手机号是否在采集状态列表: {is_monitored}")

            # 3. 如果手机号不在采集状态列表，则加入
            if not is_monitored:
                self.logger.warning(f"Payment ID {self.payment_id} 的手机号不在短信采集状态列表，正在加入...")

                # 如果已有数据，追加新的 payment_id，否则直接存储
                if existing_payments:
                    # 如果 Redis 返回的是 bytes，则先解码
                    if isinstance(existing_payments, bytes):
                        existing_payments = existing_payments.decode()

                    # 解析存储的字符串（按逗号分隔）
                    payment_list = existing_payments.split(',')
                    self.logger.info(f" 解析后的 existing_payments: '{existing_payments}'")
                    
                    updated_payments = (existing_payments + ',' + self.payment_id) if existing_payments else self.payment_id
                    self.logger.info(f" 拼接后的 updated_payments: '{updated_payments}'")
                else:
                    updated_payments = self.payment_id
                    self.logger.info(f" Redis 中无旧数据，直接使用 payment_id: '{updated_payments}'")

                await self.redis.set(redis_key, updated_payments)
                self.logger.info(f"Payment ID {self.payment_id} 已成功加入短信采集状态列表，当前列表: {updated_payments}")

            for channel in self.qr_channels:
                # 1. 打印日志，记录正在移除的 Redis 列表
                self.logger.info(f"正在从 Redis 列表 'payment_active_{channel}' 移除 payment_id: {self.payment_id}")
                await self.redis.lrem('payment_active_{}'.format(channel), 0, self.payment_id)
                self.logger.info(f"payment_id: {self.payment_id} 已从 'payment_active_{channel}' 移除")

                # 2. 打印日志，记录正在推送的 Redis 列表
                self.logger.info(f"正在将 payment_id: {self.payment_id} 推送到 Redis 列表 'payment_active_{channel}'")
                await self.redis.rpush('payment_active_{}'.format(channel), self.payment_id)
                self.logger.info(f"payment_id: {self.payment_id} 已成功推送到 'payment_active_{channel}'")
                
            # await self.redis.setex(heartbeat_key, 60, '1')  # 60 秒过期时间
            # if self.qr_channel == 1002:
            #     await self.redis.lrem('payment_active_1001', 0, self.payment_id)
            #     await self.redis.rpush('payment_active_1001', self.payment_id)
        return dict(type='Login', code=200, msg='login success.', data={'phone': payment['phone']})

        # if await self.is_null(data, ['phone_id', 'password']):
        #     await self.write_message(dict(type='Login', code=99, msg='data error'))
        # self.phone_id = data['phone_id']
        # self.partner_id = None
        # phone = await self.get_result_by_condition('phonepe', ['*'], {'id': self.phone_id})
        # if not phone or phone['pw'] != data['password']:
        #     return dict(type='Login', code=99, msg='id or pw error')
        # self.payment_id = phone['payment_id']
        # phonepe_socket[int(self.phone_id)] = self
        # await self.update_result('phonepe', {'status': 1}, {'id': self.phone_id})
        # return dict(type='Login', code=200, msg='login success.')

    async def logout(self, flag = False):
        if flag == False:
            IOLoop.current().add_callback(self.clean)
        await self.redis.srem('payment_online_ds', self.payment_id)
        # 定义 Redis Key
        redis_key = 'payment_online_ds_phone'

        # 记录日志：准备从 Redis String 中移除 payment_id
        self.logger.info(f"[开始] 从 '{redis_key}' 移除 payment_id: {self.payment_id}")

        # 获取当前存储的 payment_id 列表
        existing_payments = await self.redis.get(redis_key)

        if existing_payments:
            # 解析存储的字符串（按逗号分隔）
            # 如果 Redis 返回的是 bytes，则先解码
            if isinstance(existing_payments, bytes):
                existing_payments = existing_payments.decode()

            # 解析存储的字符串（按逗号分隔）
            payment_list = existing_payments.split(',')

            if self.payment_id in payment_list:
                # 移除指定的 payment_id
                payment_list.remove(self.payment_id)

                if payment_list:
                    # 仍有其他数据，更新 Redis
                    await self.redis.set(redis_key, ','.join(payment_list))
                    self.logger.info(f"[成功] 已从 '{redis_key}' 移除 payment_id: {self.payment_id}")
            else:
                self.logger.warning(f"[警告] payment_id: {self.payment_id} 不在 '{redis_key}' 中，无需移除")
        else:
            self.logger.warning(f"[警告] '{redis_key}' 为空，无需移除")

        for channel in self.qr_channels:
            # 记录日志：当前正在处理的 channel
            self.logger.info(f" [开始] 处理 channel: {channel}")

            # 记录日志：准备执行 lrem
            self.logger.info(f"[Step 1] 从 'payment_active_{channel}' 移除 payment_id: {self.payment_id}")

            # 执行 lrem 操作
            removed_count = await self.redis.lrem(f'payment_active_{channel}', 0, self.payment_id)

            # 记录日志：lrem 操作完成
            self.logger.info(f" [Step 1] 已从 'payment_active_{channel}' 移除 {removed_count} 个 payment_id: {self.payment_id}")

            # 记录日志：当前 channel 处理完成
            self.logger.info(f" [完成] channel: {channel} 处理完毕\n")


            # 记录日志
            self.logger.info(f"用户 {self.payment_id} 正在登出，移除在线列表")

        return dict(type='Offline', code=200, msg='logout success.')

    # 启动
    # async def start(self, data):
    #     # 启动成功更新码状态
    #     if data['status']:
    #         if not await self.update_result('payment', {'status': 1}, {'id': self.payment_id}):
    #             await self.write_message(dict(type='OTP', code=99, msg='system error'))
    #     # 启动失败置空云机
    #     if not data['status']:
    #         if not await self.update_result('phonepe', {'occupied': 0}, {'id': self.phone_id}):
    #             await self.write_message(dict(type='OTP', code=99, msg='system error'))
    #     # 通知APP
    #     data_s = dict(to='app', type='my.payment', id=self.partner_id, code=10603 if data['status'] else 10604)
    #     await self.redis.publish('phonepe_msg', json.dumps(data_s))

    # 在线下线状态
    async def qrcode_online(self, online):
        online_status_key = f'online_status_{self.payment_id}'  # 标记在线状态的 key
        await self.redis.setex(online_status_key, 300, 'online')  # 设置在线状态，5分钟过期
        if online:
            ttl = await self.redis.ttl(f'monitor_payment_online_{self.payment_id}')
            if ttl <= 0:
                if ttl == -2:
                    self.logger.info(f"Key 不存在，payment_id: {self.payment_id}")
                else:
                    self.logger.info(f"Key 已过期，payment_id: {self.payment_id}")
                await self.redis.srem('payment_online_ds', self.payment_id)
                # 定义 Redis Key
                redis_key = 'payment_online_ds_phone'

                # 记录日志：准备从 Redis String 中移除 payment_id
                self.logger.info(f"[开始] 从 '{redis_key}' 移除 payment_id: {self.payment_id}")

                # 获取当前存储的 payment_id 列表
                existing_payments = await self.redis.get(redis_key)

                if existing_payments:
                    # 解析存储的字符串（按逗号分隔）
                    # 如果 Redis 返回的是 bytes，则先解码
                    if isinstance(existing_payments, bytes):
                        existing_payments = existing_payments.decode()

                    # 解析存储的字符串（按逗号分隔）
                    payment_list = existing_payments.split(',')

                    if self.payment_id in payment_list:
                        # 移除指定的 payment_id
                        payment_list.remove(self.payment_id)

                        if payment_list:
                            # 仍有其他数据，更新 Redis
                            await self.redis.set(redis_key, ','.join(payment_list))
                            self.logger.info(f"[成功] 已从 '{redis_key}' 移除 payment_id: {self.payment_id}")
                    else:
                        self.logger.warning(f"[警告] payment_id: {self.payment_id} 不在 '{redis_key}' 中，无需移除")
                else:
                    self.logger.warning(f"[警告] '{redis_key}' 为空，无需移除")
                for channel in self.qr_channels:
                    #  记录日志：即将执行 lrem 操作
                    self.logger.info(f"开始处理 channel: {channel}，准备从 'payment_active_{channel}' 移除 payment_id: {self.payment_id}")
                    
                    # 执行 Redis lrem 操作
                    removed_count = await self.redis.lrem(f'payment_active_{channel}', 0, self.payment_id)
                    
                    # 记录日志：lrem 操作完成，打印移除的数量
                    self.logger.info(f"channel: {channel} 处理完成，已移除 {removed_count} 个 payment_id: {self.payment_id}，列表名：'payment_active_{channel}'")

                    self.logger.warning(f"用户 {self.payment_id} 掉线，正在移除在线列表")

                return dict(type='Online', code=200, msg='请联系工作人员后台开启接单.')
            await self.redis.sadd('payment_online_ds', self.payment_id)
            # 定义 Redis Key
            redis_key = 'payment_online_ds_phone'

            # 2. 查询手机号是否在采集状态列表
            existing_payments = await self.redis.get(redis_key)
            is_monitored = False

            if existing_payments:
                # 解析存储的字符串（按逗号分隔）
                # 如果 Redis 返回的是 bytes，则先解码
                if isinstance(existing_payments, bytes):
                    existing_payments = existing_payments.decode()

                # 解析存储的字符串（按逗号分隔）
                payment_list = existing_payments.split(',')
                is_monitored = self.payment_id in payment_list

            self.logger.info(f"手机号 {self.payment_id} 是否在采集状态列表: {is_monitored}")

            # 3. 如果手机号不在采集状态列表，则加入
            if not is_monitored:
                self.logger.warning(f"Payment ID {self.payment_id} 的手机号不在短信采集状态列表，正在加入...")

                # 如果已有数据，追加新的 payment_id，否则直接存储
                if existing_payments:
                    # 如果 Redis 返回的是 bytes，则先解码
                    if isinstance(existing_payments, bytes):
                        existing_payments = existing_payments.decode()

                    # 解析存储的字符串（按逗号分隔）
                    payment_list = existing_payments.split(',')
                    self.logger.info(f" 解析后的 existing_payments: '{existing_payments}'")
                    
                    updated_payments = (existing_payments + ',' + self.payment_id) if existing_payments else self.payment_id
                    self.logger.info(f" 拼接后的 updated_payments: '{updated_payments}'")
                else:
                    updated_payments = self.payment_id
                    self.logger.info(f" Redis 中无旧数据，直接使用 payment_id: '{updated_payments}'")

                await self.redis.set(redis_key, updated_payments)
                self.logger.info(f"Payment ID {self.payment_id} 已成功加入短信采集状态列表，当前列表: {updated_payments}")
                
            # 设置一个 5 分钟（300秒）的过期时间的 key
            await self.redis.setex(f'monitor_payment_online_{self.payment_id}', 300, 'active')
            # 在每个通道进行操作
            self.logger.info(f"QR Channels: {self.qr_channels}")
            for channel in self.qr_channels:
                # 记录日志：当前正在处理的 channel
                self.logger.info(f"[开始] 处理 channel: {channel}")

                # 记录日志：准备执行 lrem
                self.logger.info(f"[Step 1] 从 'payment_active_{channel}' 移除 payment_id: {self.payment_id}")

                # 执行 lrem 操作
                removed_count = await self.redis.lrem(f'payment_active_{channel}', 0, self.payment_id)

                # 记录日志：lrem 操作完成
                self.logger.info(f"[Step 1] 已从 'payment_active_{channel}' 移除 {removed_count} 个 payment_id: {self.payment_id}")

                # 记录日志：准备执行 rpush
                self.logger.info(f"[Step 2] 准备将 payment_id: {self.payment_id} 推送到 'payment_active_{channel}'")

                # 执行 rpush 操作
                await self.redis.rpush(f'payment_active_{channel}', self.payment_id)

                # 记录日志：rpush 操作完成
                self.logger.info(f"【码监控】: [Step 2] 成功将 payment_id: {self.payment_id} 推送到 'payment_active_{channel}'")

                # 记录日志：当前 channel 处理完成
                self.logger.info(f"[完成] channel: {channel} 处理完毕\n")
            
            # await self.redis.sadd('payment_online_df', self.payment_id)
            # await self.redis.lrem('payment_active_df', 0, self.payment_id)
            # await self.redis.rpush('payment_active_df', self.payment_id)

            return dict(type='Online', code=200, msg='On Success.')
        else:
            await self.redis.srem('payment_online_ds', self.payment_id)
            await self.redis.delete(online_status_key)
            # 定义 Redis Key
            redis_key = 'payment_online_ds_phone'

            # 记录日志：准备从 Redis String 中移除 payment_id
            self.logger.info(f"[开始] 从 '{redis_key}' 移除 payment_id: {self.payment_id}")

            # 获取当前存储的 payment_id 列表
            existing_payments = await self.redis.get(redis_key)

            if existing_payments:
                # 解析存储的字符串（按逗号分隔）
                # 如果 Redis 返回的是 bytes，则先解码
                if isinstance(existing_payments, bytes):
                    existing_payments = existing_payments.decode()

                # 解析存储的字符串（按逗号分隔）
                payment_list = existing_payments.split(',')

                if self.payment_id in payment_list:
                    # 移除指定的 payment_id
                    payment_list.remove(self.payment_id)

                    if payment_list:
                        # 仍有其他数据，更新 Redis
                        await self.redis.set(redis_key, ','.join(payment_list))
                        self.logger.info(f"[成功] 已从 '{redis_key}' 移除 payment_id: {self.payment_id}")
                else:
                    self.logger.warning(f"[警告] payment_id: {self.payment_id} 不在 '{redis_key}' 中，无需移除")
            else:
                self.logger.warning(f"[警告] '{redis_key}' 为空，无需移除")
            for channel in self.qr_channels:
                #  记录日志：即将执行 lrem 操作
                self.logger.info(f"开始处理 channel: {channel}，准备从 'payment_active_{channel}' 移除 payment_id: {self.payment_id}")
                
                # 执行 Redis lrem 操作
                removed_count = await self.redis.lrem(f'payment_active_{channel}', 0, self.payment_id)
                
                # 记录日志：lrem 操作完成，打印移除的数量
                self.logger.info(f"channel: {channel} 处理完成，已移除 {removed_count} 个 payment_id: {self.payment_id}，列表名：'payment_active_{channel}'")
                
                self.logger.warning(f"用户 {self.payment_id} 掉线，正在移除在线列表")
                
            return dict(type='Online', code=200, msg='Off success.')
        # heartbeat_key = f'heartbeat:{self.payment_id}'  # 辅助key，维持心跳状态
        # if online:
        #     await self.redis.setex(heartbeat_key, 60, '1')  # 60 秒过期时间
        #     return dict(type='Online', code=200, msg='on success.')

    async def process_message(self, from_param, content):
        match self.bank_type:
            # AX-MAHABK→MAHARASTRA BANK
            case "MAHARASTRA BANK":
                self.logger.info("SMS 处理 {} AX-MAHABK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                # 检查 from_param 是否和银行编号一致
                # if not from_param == 'AX-MAHABK':
                from_param = from_param.strip()  # 去除空格
                # from_param_suffix = from_param.split('-')[-1].strip()  # 截取 '-' 后的部分并去除空格
                # if from_param_suffix != 'MAHABK':
                #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                if re.search(r'MAHABK(-S)?$', from_param):
                    self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                else:
                    self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                    return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))

                # 提取金额 (支持 "Rs" 和 "INR" 格式)
                amount_pattern = r'(?:Rs|INR) ([0-9,]+\.\d{2})'
                amount_match = re.search(amount_pattern, content)
                if amount_match:
                    amount = amount_match.group(1).replace(',', '').strip()
                    data['amount'] = amount
                else:
                    # self.logger.error("SMS {} 无法解析金额".format(self.bank_type))
                    # return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    self.logger.error("SMS {} 无法解析金额，进入备用规则".format(self.bank_type))

                    # **备用规则：** 解析 `Rs` 和金额（如果原规则解析失败）
                    backup_amount_pattern = r'Rs\.\s*([0-9,]+\.\d{2})'  # 匹配 "Rs." 后的金额
                    backup_amount_match = re.search(backup_amount_pattern, content)
                    if backup_amount_match:
                        amount = backup_amount_match.group(1).replace(',', '').strip()
                        self.logger.info(f"Backup Amount found: {amount}")
                        data['amount'] = amount
                    else:
                        # self.logger.error("SMS {} 备用规则也无法解析金额".format(self.bank_type))
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                # 提取交易参考号 (支持 "UPI:", "UPI RRN:" 和 "UPI:xxx-yyy" 格式)
                utr_pattern = r'UPI(?: RRN)?[: ](\d+)-?[A-Z]*'
                utr_match = re.search(utr_pattern, content)
                if utr_match:
                    utr = utr_match.group(1)
                    data['utr'] = utr
                else:
                    # self.logger.error("SMS {} 无法解析 UTR".format(self.bank_type))
                    # return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))
                    self.logger.error("SMS {} 无法解析 UTR，进入备用规则".format(self.bank_type))

                    # **备用规则：** 解析 `RRN` 格式
                    backup_utr_pattern = r'RRN: (\d+)'  # 匹配 RRN
                    backup_utr_match = re.search(backup_utr_pattern, content)
                    if backup_utr_match:
                        utr = backup_utr_match.group(1)
                        self.logger.info(f"Backup UTR found: {utr}")
                        data['utr'] = utr
                    else:
                        # self.logger.error("SMS {} 备用规则也无法解析 UTR".format(self.bank_type))
                        self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))
                return data  # 返回解析后的数据字典

            # AD、BP、VK、VM、QP、BP、JD、CP、AX、VZ、JM、BT、BR、VD、MD、JG 和 JX→CANARA BANK 
            case "CANARA BANK":
                self.logger.info("SMS 处理 {} CANARA-BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                # 定义允许的银行标识符数组
                # allowed_bank_identifiers = [
                #     'AD-CANBNK', 'BP-CANBNK', 'VK-CANBNK', 'VM-CANBNK', 'QP-CANBNK',
                #     'BP-CANBNK', 'JD-CANBNK', 'CP-CANBNK', 'AX-CANBNK', 'VZ-CANBNK',
                #     'JM-CANBNK', 'BT-CANBNK', 'BR-CANBNK', 'VD-CANBNK', 'MD-CANBNK',
                #     'JG-CANBNK', 'JX-CANBNK'
                # ]
                
                try:
                    # 检查 from_param 是否在允许的银行标识符数组中
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 截取 '-' 后的部分并去除空格
                    # if from_param_suffix != 'CANBNK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    if re.search(r'CANBNK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    
                    # 提取金额
                    try:
                        amount_match = re.search(r'Rs\.([0-9,]+\.\d{2})', content)
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            # 新的解析规则，增加对 INR 或 ₹ 的支持
                            amount_match = re.search(r'(INR|₹)\s*([0-9,]+\.\d{2})', content)
                            if amount_match:
                                amount = amount_match.group(2).replace(',', '').strip()
                                data['amount'] = amount
                            else:
                                # raise ValueError("无法解析金额")
                                self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                                return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号 (UPI Ref no 后的数字)
                    try:
                        utr_match = re.search(r'UPI Ref no (\d+)', content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UTR")
                            # 新的解析规则：解析 UPI-ID 后的数字，尝试获取 UPI 参考号
                            utr_match = re.search(r'UPI-ID\s*[\d\w\-\@]+.*\((UPI Ref no\s*(\d+))\)', content)
                            if utr_match:
                                utr = utr_match.group(2)
                                data['utr'] = utr
                            else:
                                self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                                return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))

                    # 返回解析后的数据字典
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "SBI BANK":
                self.logger.info("SMS 处理 {} SBI-BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否在允许的银行标识符数组中
                    from_param = from_param.strip()  # 去除空格
                    from_param_suffix = from_param.split('-')[-1].strip()  # 截取 '-' 后的部分并去除空格
                    if from_param_suffix != 'SBIUPI':
                        self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 提取金额
                    try:
                        amount_match = re.search(r'Rs\.\s*([\d,]+(?:\.\d{2})?)', content)
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号 (UPI Ref no 后的数字)
                    try:
                        utr_match = re.search(r'Ref No (\d+)', content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UTR")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))

                    # 返回解析后的数据字典
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
                
            case "DHAN BANK":
                self.logger.info("SMS 处理 {} DHAN-BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否在允许的银行标识符数组中
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 截取 '-' 后的部分并去除空格
                    # if from_param_suffix != 'DHANBK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 直接判断是否匹配 DHANBK 或 DHANBK-S 结尾
                    if re.search(r'DHANBK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 提取金额
                    try:
                        # 匹配金额
                        amount_pattern = r'Rs\.([\d,]+\.\d{2})'
                        amount_match = re.search(amount_pattern, content)
                        if not amount_match:
                            # 匹配示例：INR 30.00 is credited
                            amount_pattern_alt = r'INR ([\d,]+\.\d{2})\s+is\s+credited'
                            amount_match = re.search(amount_pattern_alt, content)
                        
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号 (UPI Ref no 后的数字)
                    try:
                        atr_pattern = r'UPI Ref no (\w+)'
                        utr_match = re.search(atr_pattern, content)
                        if not utr_match:
                            # 匹配示例：UPI TXN: /384037727312-GIRI KUMAR
                            utr_pattern_alt = r'UPI TXN: \/(\d+)'
                            utr_match = re.search(utr_pattern_alt, content)
                        
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UTR")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))

                    # 返回解析后的数据字典
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
                
            case "BOB BANK":
                self.logger.info("SMS 处理 {} BOB-BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否在允许的银行标识符数组中
                    from_param = from_param.strip()  # 去除空格
                    if re.search(r'BOBSMS(-S)?$', from_param) or re.search(r'BOBTXN(-S)?$', from_param) or re.search(r'BOBOTP(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 提取金额
                    try:
                        # 匹配金额
                        amount_pattern = r"Rs\.(\d+(?:\.\d{1,2})?) Credited"
                        amount_match = re.search(amount_pattern, content)

                        if not amount_match:
                            # 匹配示例：INR 30.00
                            amount_pattern_alt = r'INR ([\d,]+\.\d{2})'
                            amount_match = re.search(amount_pattern_alt, content)

                        if not amount_match:
                            # 匹配示例：credited with 500.00
                            amount_pattern_alt = r'credited with (\d+\.\d{2})'
                            amount_match = re.search(amount_pattern_alt, content)
                    
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号 (UPI Ref no 后的数字)
                    try:
                        atr_pattern = r'UPI/(\w+)'
                        utr_match = re.search(atr_pattern, content)

                        if not utr_match:
                            # 匹配示例：UPI Ref No 217462105615
                            utr_pattern_alt = r'UPI Ref No (\d+)'
                            utr_match = re.search(utr_pattern_alt, content)
                        
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UTR")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))

                    # 返回解析后的数据字典
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
            case "IDBI BANK":
                self.logger.info("SMS 处理 {} IDBI-BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否在允许的银行标识符数组中
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 截取 '-' 后的部分并去除空格
                    # if from_param_suffix != 'IDBIBK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 直接判断是否匹配 INDBNK 或 INDBNK-S 结尾
                    if re.search(r'IDBIBK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 提取金额
                    try:
                        # 旧规则：匹配 Rs. 后金额，形如 Rs 15.00 或 Rs.15.00
                        amount_pattern = r'Rs\. ?(\d+\.\d{2})'
                        amount_match = re.search(amount_pattern, content)
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '')
                            data['amount'] = amount
                        else:
                            # 新规则1：匹配 INR 后金额
                            alt_amount_pattern1 = r'INR ([\d,]+\.\d{2})'
                            alt_amount_match1 = re.search(alt_amount_pattern1, content)
                            if alt_amount_match1:
                                amount = alt_amount_match1.group(1).replace(',', '')
                                data['amount'] = amount
                            else:
                                # 新规则2：匹配形如 Rs 15,000.00 (含逗号和无小数的情况你可自己扩展)
                                alt_amount_pattern2 = r'Rs\.? ?([\d,]+\.\d{2})'
                                alt_amount_match2 = re.search(alt_amount_pattern2, content)
                                if alt_amount_match2:
                                    amount = alt_amount_match2.group(1).replace(',', '')
                                    data['amount'] = amount
                                else:
                                    self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                                    return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号
                    try:
                        atr_pattern = r'UPI:(\d+)'
                        utr_match = re.search(atr_pattern, content)
                        if utr_match:
                            data['utr'] = utr_match.group(1)
                        else:
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析 UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))

                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
            case "INDIAN BANK":
                self.logger.info("SMS 处理 {} INDIA BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    # if from_param_suffix != 'INDBNK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 直接判断是否匹配 INDBNK 或 INDBNK-S 结尾
                    if re.search(r'INDBNK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 提取金额
                    try:
                        amount_pattern = r'Rs\. (\d+\.\d{2})'  # 匹配 Rs. 后面的金额
                        amount_match = re.search(amount_pattern, content)
                        if amount_match:
                            amount = amount_match.group(1)
                            data['amount'] = amount
                        else:
                            # 备用规则: 匹配 "credited to a/c" 前面的金额
                            self.logger.info("SMS {} 提取金额 备用规则 ".format(self.bank_type))
                            alt_amount_pattern = r'([\d,]+\.\d{2}) credited to a/c'
                            alt_amount_match = re.search(alt_amount_pattern, content)
                            if alt_amount_match:
                                amount = alt_amount_match.group(1).replace(',', '').replace(' ', '')  # 去掉逗号
                                data['amount'] = amount
                            else:
                                # raise ValueError("无法解析金额")
                                self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                                return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号
                    try:
                        utr_pattern = r'UPI Ref no (\d+)'  # 匹配 UPI Ref no 后的数字
                        utr_match = re.search(utr_pattern, content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UTR")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))
                    
                    # 返回解析后的数据字典
                    return data

                except Exception as e:
                    # self.logger.error("处理 {} 时发生未知错误: {}".format(self.bank_type, str(e)))
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "PSB BANK":
                self.logger.info("SMS 处理 {} PSB-BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否在允许的银行标识符数组中
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 截取 '-' 后的部分并去除空格
                    if re.search(r'PSBANK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    
                    # 提取金额
                    try:
                        amount_match = re.search(r'(?<=with Rs\s)(\d+)', content)
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            self.logger.warning("无法根据初始规则解析金额，尝试备用规则")
                            amount_match_alt = re.search(r'Credited with Rs (\d+\.?\d*)', content)
                            if amount_match_alt:
                                amount = amount_match_alt.group(1).strip()
                                data['amount'] = amount
                            else:
                                self.logger.warning("备用规则 1 失败，尝试备用规则 2")

                                # 备用规则 2: "Rs. X,XXX.XX" 这种带逗号格式的金额
                                amount_match_alt2 = re.search(r'Rs\.?\s*([\d,]+\.\d{2})', content)
                                if amount_match_alt2:
                                    amount = amount_match_alt2.group(1).replace(',', '').strip()  # 移除逗号
                                    data['amount'] = amount
                                else:
                                    # raise ValueError("无法解析金额")
                                    self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                                    return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号
                    try:
                        utr_match = re.search(r'UPVCR/(\d+)', content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            self.logger.warning("无法根据初始规则解析 UTR，尝试备用规则")
                            utr_match_alt = re.search(r'UPI/CR/(\d+)', content)
                            if utr_match_alt:
                                utr = utr_match_alt.group(1).strip()
                                data['utr'] = utr
                            else:
                                # data['utr'] = None  # 如果UTR无法匹配，设置为None
                                self.logger.warning("备用规则 2 失败，尝试备用规则 3")
                                utr_match = re.search(r'(?i)(?:UPI Ref no|Ref no|UPVCR/|UPI/CR/)\s*(\d+)', content)
                                if utr_match:
                                    data['utr'] = utr_match.group(1).strip()
                                else:
                                    # raise ValueError("无法解析 UTR")
                                    self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                                    return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))

                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析 UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))

                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "AUNEW BANK":
                self.logger.info("SMS 处理 {} AUNEW BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    if from_param_suffix != 'FNCARE':
                        self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))

                    # 提取金额
                    try:
                        amount_pattern = r'Rs (\d+\.\d+) Cr'  # 匹配 Rs 后面的金额
                        amount_match = re.search(amount_pattern, content)
                        if amount_match:
                            amount = amount_match.group(1)
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 utr
                    try:
                        rrn_pattern = r'RRN (\d+)'  # 匹配 RRN 后的数字
                        rrn_match = re.search(rrn_pattern, content)
                        if rrn_match:
                            rrn = rrn_match.group(1)
                            data['utr'] = rrn
                        else:
                            # raise ValueError("无法解析 utr")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        # self.logger.error("无法解析 utr\n%s", json.dumps(error_info, indent=4))
                        self.logger.error("无法解析 UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the RRN'.format(self.bank_type))

                    # 返回解析后的数据字典
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "JANA BANK":
                self.logger.info("SMS 处理 {} JANA BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    # if from_param_suffix != 'JANABK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    if re.search(r'JANABK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    
                    # 提取金额
                    try:
                        amount_pattern = r'credited with Rs (\d+\.\d+)'  # 匹配金额
                        amount_match = re.search(amount_pattern, content)
                        if not amount_match:
                            # 尝试新规则：credited with INR
                            amount_pattern_alt = r'credited with INR ([\d,]+\.\d+)'
                            amount_match = re.search(amount_pattern_alt, content)
                        if amount_match:
                            amount = amount_match.group(1).replace(",", "").replace(" ", "")  # 去除金额中的空格和逗号
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号
                    try:
                        utr_pattern = r'UPI Ref no (\d+)'  # 匹配 UPI 参考号
                        utr_match = re.search(utr_pattern, content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UPI 参考号")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析 UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "KARNATAKA BANK":
                self.logger.info("SMS 处理 {} KARNATAKA BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    # if from_param_suffix != 'KBLBNK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    if re.search(r'KBLBNK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    
                    # 提取金额
                    try:
                        amount_pattern = r'credited for Rs\.(\d+\.\d+)'  # 匹配金额
                        amount_match = re.search(amount_pattern, content)
                        if not amount_match:
                            # 备用模式（没有小数也处理一下，比如 Rs.1000）
                            alt_pattern = r'credited for Rs\.([\d,]+)'
                            amount_match = re.search(alt_pattern, content)
                        if amount_match:
                            amount = amount_match.group(1).replace(",", "").replace(" ", "")
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号
                    try:
                        utr_pattern = r'UPI Ref no (\d+)'  # 匹配 UPI 参考号
                        utr_match = re.search(utr_pattern, content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UPI 参考号")
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析 UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "JK BANK":
                self.logger.info("SMS 处理 {} JK BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    # if from_param_suffix != 'JKBANK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    if re.search(r'JKBANK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    
                    # 有账户余额类型格式的信息不参与匹配，此格式信息是重复的
                    # if 'Available Bal' in content:
                    #     return dict(type='New', code=99, msg='{} Information in this type of format does not participate in matching'.format(self.bank_type))

                    # 提取金额
                    try:
                        # 允许逗号的金额格式，如 Rs. 10,000.00
                        amount_pattern = r'Rs\.\s*([\d,]+\.\d{2})'  # 匹配金额
                        amount_match = re.search(amount_pattern, content)

                        if not amount_match:
                            # 备用规则：匹配 Credited by INR 1000 或者 Credited by INR 20,000
                            amount_pattern_alt = r'Credited by INR\s*([\d,]+)'
                            amount_match = re.search(amount_pattern_alt, content)

                        if amount_match:
                            amount = amount_match.group(1).replace(",", "").replace(" ", "")  # 去除金额中的空格和逗号
                            data['amount'] = amount
                        else:
                            # raise ValueError("无法解析金额")
                            self.logger.warning(
                                "[{}] 金额解析失败，尝试过 Rs. 和 INR 格式，短信内容:\n{}".format(self.bank_type, content)
                            )
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        # self.logger.error("SMS {} 无法解析金额: {}".format(self.bank_type, str(e)))
                        # 捕获异常并打印详细信息
                        stack_trace = traceback.format_exc()
                        # 错误信息
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        # 使用 %s 占位符格式化日志消息
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

                    # 提取 UPI 参考号
                    try:
                        utr_pattern = r'transaction reference number\s*(\d+)'  # 匹配 UPI 参考号
                        utr_match = re.search(utr_pattern, content)

                        if not utr_match:
                            # 备用规则：匹配 UPI/HDFC/371611587548/CR/
                            utr_pattern_alt = r'UPI/[A-Z]+/(\d+)/CR'
                            utr_match = re.search(utr_pattern_alt, content)

                        if not utr_match:
                            # 新增兼容格式：UPI Ref No: 765120944939
                            utr_pattern_alt2 = r'UPI Ref No[:：]?\s*(\d{6,})'
                            utr_match = re.search(utr_pattern_alt2, content)

                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            # raise ValueError("无法解析 UPI 参考号")
                            self.logger.warning(
                                "[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content)
                            )
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        # self.logger.error("SMS {} 无法解析 UPI 参考号: {}".format(self.bank_type, str(e)))
                        # 捕获异常并打印详细信息
                        stack_trace = traceback.format_exc()
                        # 错误信息
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        # 使用 %s 占位符格式化日志消息
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
            
                        return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    # self.logger.error("处理 {} 时发生未知错误: {}".format(self.bank_type, str(e)))
                    stack_trace = traceback.format_exc()
                    # 错误信息
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    # 使用 %s 占位符格式化日志消息
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "CGGB BANK":
                self.logger.info("SMS 处理 {} CGGB BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    if from_param_suffix != 'CGGBNK':
                        self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))

                    # 提取金额
                    amount_pattern = r'Rs\.\s*(\d+(?:\.\d{1,2})?)'  # 匹配 "Rs." 后面的金额，支持小数
                    amount_match = re.search(amount_pattern, content)
                    if amount_match:
                        data["amount"] = amount_match.group(1).replace(",", "").replace(" ", "")
                    else:
                        # self.logger.error("无法解析金额: {}".format(content))
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": "{} Unable to resolve the amount".format(self.bank_type)}

                    # 提取 UPI 参考号（支持大小写变化，冒号和空格分隔符）
                    utr_pattern = r'UPI\s*Ref\s*No[:\s]*(\d+)|UPI\s*Ref\s*no[:\s]*(\d+)'  # 支持 "No" 和 "no" 等变体
                    utr_match = re.search(utr_pattern, content)
                    if utr_match:
                        # 获取匹配到的 UPI 参考号，两个组中的一个将被捕获
                        utr = utr_match.group(1) if utr_match.group(1) else utr_match.group(2)
                        data["utr"] = utr
                    else:
                        # self.logger.error("无法解析 UPI 参考号: {}".format(content))
                        self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": "{} Unable to resolve the UPI Ref no".format(self.bank_type)}

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "TMB BANK":
                self.logger.info("SMS 处理 {} TMB BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                try:
                    # # 检查 from_param 是否符合预期银行标识
                    # from_param = from_param.strip()  # 去除空格
                    # from_param_suffix = from_param.split('-')[-1].strip()  # 提取 '-' 后的部分
                    # if from_param_suffix != 'TMBANK':
                    #     self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                    #     return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    from_param = from_param.strip()  # 去除空格
                    if re.search(r'TMBANK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))

                    # 提取金额
                    amount_pattern = r'Rs\.\s*([\d,]+(?:\.\d{1,2})?)'
                    amount_match = re.search(amount_pattern, content)
                    if amount_match:
                        data["amount"] = amount_match.group(1).replace(",", "").replace(" ", "").strip()
                    else:
                        # self.logger.error("无法解析金额: {}".format(content))
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": "{} Unable to resolve the amount".format(self.bank_type)}

                    # 提取 UPI 参考号（只匹配 UPI Ref No）
                    utr_pattern = r'UPI\s*Ref\s*No\.?\s*(\d+)'  # 只匹配 UPI Ref No 后面的数字部分
                    utr_match = re.search(utr_pattern, content)

                    # 打印匹配的内容
                    if utr_match:
                        self.logger.info("UPI Ref Match Groups: " + str(utr_match.groups()))
                        # 获取参考号
                        data["utr"] = utr_match.group(1)
                    else:
                        # self.logger.error("无法解析 UPI 参考号: {}".format(content))
                        self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": "{} Unable to resolve the UPI Ref no".format(self.bank_type)}

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
             
            case "KVB BANK":
                self.logger.info("SMS 处理 {} KVB BANK 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    # 记录初始输入参数
                    self.logger.info("检查 from 参数，当前值: {}".format(from_param))
                    # 定义新的正则表达式
                    from_param_pattern_adjusted = r'^(VD-|VM-|BT-|AD-|VA-)?(KVBANK|KVBUPI|WLITXN)(-S)?$'
                    if re.search(from_param_pattern_adjusted, from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))

                    # 提取金额
                    amount_pattern = r'Rs\.\s*([\d,]+(?:\.\d{1,2})?)'
                    amount_match = re.search(amount_pattern, content)
                    if amount_match:
                        data["amount"] = amount_match.group(1).replace(",", "").replace(" ", "").strip()
                    else:
                        # self.logger.error("无法解析金额: {}".format(content))
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": "{} Unable to resolve the amount".format(self.bank_type)}

                    # 提取 UPI 参考号（匹配 Transaction ID 后面的数字部分）
                    # Updated to capture 'P2A/TransactionID' pattern
                    utr_pattern = r'(?:Transaction\s*ID[:\s]*|P2A/)([\d]+)'
                    utr_match = re.search(utr_pattern, content)
                    if not utr_match:
                        utr_match = re.search(r'RRN#(\d+)', content)
                    # 打印匹配的内容
                    if utr_match:
                        self.logger.info("Transaction ID Match Groups: " + str(utr_match.groups()))
                        # 获取参考号
                        data["utr"] = utr_match.group(1)
                    else:
                        # self.logger.error("无法解析 Transaction ID: {}".format(content))
                        self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": "{} Unable to resolve the Transaction ID".format(self.bank_type)}

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
            
            
            case "KGB BANK DELETED": # 2025-05-28 短信utr与银行utr对不上  移除这个解析功能
                """
                解析 Kerala Gramin Bank (KGB BANK) 短信，提取金额和 UPI 参考号
                :param from_param: 短信发送方号码
                :param content: 短信内容
                :return: 解析后的字典数据或错误信息
                """
                self.logger.info(f"SMS 处理 {self.bank_type} 类型的消息")
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典

                try:
                    # 检查 from_param 是否符合 KGB BANK 标识
                    from_param = from_param.strip()  # 去除空格
                    if re.search(r'KGBANK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    # 提取金额
                    amount_pattern = r'INR\s*([\d,]+)'  # 匹配 "INR" 后面的金额
                    amount_match = re.search(amount_pattern, content)
                    if amount_match:
                        amount = amount_match.group(1).replace(",", "").replace(" ", "").strip()
                        data['amount'] = amount
                    else:
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": f"{self.bank_type} Unable to resolve the amount"}

                    # 提取 UPI 参考号
                    utr_pattern = r'UPI Ref\. no\. (\d+)'  # 匹配 "UPI Ref. no." 后的数字
                    utr_match = re.search(utr_pattern, content)
                    if utr_match:
                        utr = utr_match.group(1)
                        data['utr'] = utr
                    else:
                        self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99, "msg": f"{self.bank_type} Unable to resolve the Transaction ID"}

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error(f"Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg=f"{self.bank_type} Unknown error occurred")

            case "BOI BANK":
                self.logger.info("SMS 处理 {} 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}
                try:
                    from_param = from_param.strip()
                    if re.search(r'BOIIND(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    try:
                        amount_pattern = r'Rs\.\s*(\d{1,3}(?:,\d{3})*\.\d{2})'
                        amount_match = re.search(amount_pattern, content)

                        if not amount_match:
                            amount_pattern = r'Rs\.\s*(\d+(?:,\d{3})*\.\d{2})'
                            amount_match = re.search(amount_pattern, content)

                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    
                    try:
                        utr_pattern = r'UPI ref No.(\d+)'
                        utr_match = re.search(utr_pattern, content)
                        if not utr_match:
                            utr_pattern_alt = r'UPI Ref no (\d+)'
                            utr_match = re.search(utr_pattern_alt, content)
                        
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))
                    return data
                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "NESFB BANK":
                self.logger.info("SMS 处理 {} 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                try:
                    from_param = from_param.strip()
                    if re.search(r'NESFBK(-S)?$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号 ❌不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))
                    try:
                        amount_pattern = r'Rs\.\s*([\d,]+(?:\.\d{1,2})?)'
                        amount_match = re.search(amount_pattern, content)
                        if amount_match:
                            amount = amount_match.group(1).replace(',', '').strip()
                            data['amount'] = amount
                        else:
                            self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))
                        
                    try:
                        utr_pattern = r'UPI\s*Ref:\s*(\d+)'
                        utr_match = re.search(utr_pattern, content)
                        if utr_match:
                            utr = utr_match.group(1)
                            data['utr'] = utr
                        else:
                            self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                            return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        error_info = {
                            'error_type': type(e).__name__,
                            'error_message': str(e),
                            'stack_trace': stack_trace,
                            'content': content
                        }
                        self.logger.error("无法解析UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                        return dict(type='New', code=99, msg='{} Unable to resolve the UTR'.format(self.bank_type))
                    return data
                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))
            case "CITY UNION BANK":
                return await self.extract_amount_utr(from_param, content, r'Rs\.(\d{1,3}(?:,\d{3})*\.\d{2})', r'UPI Ref no (\d+)')

            case "EQUITAS":
                self.logger.info("SMS 处理 {} EQUITAS 类型的消息".format(self.bank_type))
                data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
                try:
                    # 检查 from_param 是否符合预期银行标识
                    from_param = from_param.strip()  # 去除空格
                    # 记录初始输入参数
                    self.logger.info("检查 from 参数，当前值: {}".format(from_param))
                    if re.search(r'^(AX-|JK-|JD-|JM-|VM-|JX-|AD-){1}EQUTAS(-S){1}$', from_param):
                        self.logger.info("SMS {} from 参数与银行编号 ✅合法".format(self.bank_type))
                    else:
                        self.logger.error("SMS {} from 参数与银行编号不一致".format(self.bank_type))
                        return dict(type='New', code=99, msg='{} incorrect sending number'.format(self.bank_type))

                    # 提取金额
                    amount_pattern = r'INR\s*([\d,]+(\.\d{1,2})?)\s*credited\s*via\s*UPI\s*to\s*Equitas'
                    amount_match = re.search(amount_pattern, content)
                    if amount_match:
                        data["amount"] = amount_match.group(1).replace(",", "").replace(" ", "").strip()
                    else:
                        # self.logger.error("无法解析金额: {}".format(content))
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99,"msg": "{} Unable to resolve the amount".format(self.bank_type)}

                    # 提取 UPI 参考号（匹配 Transaction ID 后面的数字部分）
                    # Updated to capture 'P2A/TransactionID' pattern
                    utr_pattern = r'Ref:(\d+)'
                    utr_match = re.search(utr_pattern, content)
                    # 打印匹配的内容
                    if utr_match:
                        self.logger.info("Transaction ID Match Groups: " + str(utr_match.groups()))
                        # 获取参考号
                        data["utr"] = utr_match.group(1)
                    else:
                        # self.logger.error("无法解析 Transaction ID: {}".format(content))
                        self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return {"type": "New", "code": 99,"msg": "{} Unable to resolve the Transaction ID".format(self.bank_type)}

                    # 返回解析后的数据
                    return data

                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                        'content': content
                    }
                    self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
                    return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

            case "其他银行类型":
                self.logger.info("SMS 处理其他类型的消息")
                # 其他银行类型的处理逻辑
                return dict(type='New', code=99, msg='Unable to resolve the SMS')
            case _:
                self.logger.warning(f"SMS 未知的 from 参数: {from_param}")
                return dict(type='New', code=99, msg='Unable to resolve the SMS')

    async def extract_amount_utr(self, from_param, content, amount_pattern, utr_pattern):
        """
        提取金额与utr
        amount_pattern: 金额的正则匹配规则
        utr_pattern: utr或UPI的匹配规则
        from_name: 需要匹配的信息来源银行名 如: JM-CUBLTD JM-CUBANK
        """
        self.logger.info("SMS 处理 {} 类型的消息".format(self.bank_type))
        data = {'trade_type': 1, 'code': ''}  # 初始化数据字典
        try:
            # 检查 from_param 是否符合预期银行标识
            from_param = from_param.strip()  # 去除空格
            if re.search(r'(CUBLTD|CUBANK|CUBLTD-S|CUBANK-S)$', from_param):
                self.logger.info(f"SMS {self.bank_type} from 参数与银行编号 ✅合法")
            else:
                self.logger.error(f"SMS {self.bank_type} from 参数与银行编号 ❌不一致")
                return dict(type='New', code=99, msg=f'{self.bank_type} incorrect sending number')
            # 提取金额
            try:
                amount_match = re.search(amount_pattern, content)
                if amount_match is not None:
                    amount = amount_match.group(1).replace(",", "").replace(" ", "")  # 去除金额中的空格和逗号
                    data['amount'] = amount
                else:
                    # raise ValueError("无法解析金额")
                    # 备用规则匹配金额
                    fallback_amount_pattern = r'credited for Rs\.(\d+\.\d{2})'
                    amount_match = re.search(fallback_amount_pattern, content)
                    if amount_match:
                        amount = amount_match.group(1).replace(",", "").replace(" ", "").strip()
                        data['amount'] = amount
                    else:
                        # self.logger.error(f"SMS {self.bank_type} 无法解析金额: 无法解析金额")
                        self.logger.warning("[{}] 金额解析失败，短信内容:\n{}".format(self.bank_type, content))
                        return dict(type='New', code=99, msg=f'{self.bank_type} Unable to resolve the amount')
                    # raise ValueError("无法解析金额")
            except Exception as e:
                # self.logger.error("SMS {} 无法解析金额: {}".format(self.bank_type, str(e)))
                stack_trace = traceback.format_exc()
                error_info = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'stack_trace': stack_trace,
                    'content': content
                }
                self.logger.error("无法解析金额：\n%s", json.dumps(error_info, indent=4))
                return dict(type='New', code=99, msg='{} Unable to resolve the amount'.format(self.bank_type))

            # 提取 UPI 参考号
            try:
                utr_match = re.search(utr_pattern, content)
                if utr_match:
                    utr = utr_match.group(1)
                    data['utr'] = utr
                else:
                    # raise ValueError("无法解析 UPI 参考号")
                    self.logger.warning("[{}] UPI 参考号解析失败，短信内容:\n{}".format(self.bank_type, content))
                    return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))
            except Exception as e:
                # self.logger.error("SMS {} 无法解析 UPI 参考号: {}".format(self.bank_type, str(e)))
                stack_trace = traceback.format_exc()
                error_info = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'stack_trace': stack_trace,
                    'content': content
                }
                self.logger.error("无法解析 UPI 参考号：\n%s", json.dumps(error_info, indent=4))
                return dict(type='New', code=99, msg='{} Unable to resolve the UPI Ref no'.format(self.bank_type))

            # 返回解析后的数据
            return data

        except Exception as e:
            # self.logger.error("处理 {} 时发生未知错误: {}".format(self.bank_type, str(e)))
            stack_trace = traceback.format_exc()
            error_info = {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'stack_trace': stack_trace,
                'content': content
            }
            self.logger.error("Unknown error occurred：\n%s", json.dumps(error_info, indent=4))
            return dict(type='New', code=99, msg='{} Unknown error occurred'.format(self.bank_type))

    def check_process_message(self, data):
        """处理接收到的消息并验证签名及消息内容"""
        data_r = dict()
        try:
            data_r['from'] = data['from']
            data_r['sign'] = data['sign']
            data_r['content'] = data['content']
            data_r['received_time'] = data['received_time']
        except Exception as e:
            self.logger.exception(e)
            return dict(type='New', code=99, msg='错误：参数错误')

        # 验证签名
        str_to_verify = f'type=New&content={data_r["content"]}&from={data_r["from"]}&received_time={data_r["received_time"]}'
        calculated_sign = Websocket.generate_md5(self, str_to_verify)

        if calculated_sign != data_r['sign']:
            return dict(type='New', code=99, msg='Sign wrong')

        # 如果都匹配成功
        return {'status': '成功：消息验证通过', 'code': 200}

    def generate_md5(self, data):
        """生成MD5签名"""
        md5 = hashlib.md5()
        md5.update(data.encode(encoding='UTF-8'))
        return md5.hexdigest()

    async def new_record(self, data_post):
        # 请求的数据格式:
        # data = {
        #     'type': 'New',
        #     'content': 'Your A/c No:XX3698 has been credited with Rs.2000.00 on 23-08-2024 12:26:04 from UPI-ID 9309301453@ybl (UPI Ref no 423601508686).-Canara Bank'
        # }

        # 检查IP 地址
        # if self.request.remote_ip in ['127.0.0.1', '::1']:
        #     return dict(code=99, msg=json.dumps(response_data))
        # 记录 data_post 传递的值
        self.logger.info(f'Data post received:{data_post}')

        # 调用处理消息的封装方法
        response_data =  Websocket.check_process_message(self, data_post)
        # 判断 response 的返回数据 code 是否是 99，如果是 99，打印提示
        if response_data.get('code') == 99:
            response_data['data'] = data_post
            return response_data
        data = await Websocket.process_message(self, data_post['from'], data_post['content'])
        # 检查并删除非空的键
        keys_to_delete = ['content', 'from', 'sign']
        for key in keys_to_delete:
            if key in data and data[key]:  # 检查键是否存在且值非空
                del data[key]

        # 写入短信表 
        data_sms = dict()
        data_sms['frm'] = data_post['from']
        data_sms['content'] = data_post['content']
        data_sms['received_time'] = data_post['received_time']
        if await self.is_null(data, ['trade_type', 'amount', 'utr']):
            data_sms['remark'] = "失败解析，码商：{}".format(self.partner_id)
            data_sms['payment_id'] = self.payment_id
            data_sms['status'] = 0 # 解析短信失败
            await self.create_result('sms_record', data_sms)
            data['data'] = data_post
            return data
            # return dict(type='New', code=99, msg='Abnormal data')
        data_sms['remark'] = "成功解析，码商：{},amount:{},utr:{}".format(self.partner_id, data['amount'], data['utr'])
        data_sms['payment_id'] = self.payment_id
        data_sms['status'] = 1 # 解析短信成功
        await self.create_result('sms_record', data_sms)

        # 使用锁，5s使用自旋锁, 防止取消的同时回调 必须是有utr字段
        if 'utr' in data.keys() and data['utr']:
            count_circle = 0
            while True:
                busy_key = 'success_busy_{utr}'.format(utr=data['utr'])
                if await self.redis.setnx(busy_key, 1):
                    await self.redis.expire(busy_key, 10)
                    break
                if count_circle >= 10:
                    self.logger.warning(
                        'utr:{utr}Do not operate frequently'.format(utr=data['utr']))
                    res = dict(code=99, msg='Do not operate frequently',data=data_post)
                    return await self.json_response(res)
                time.sleep(0.2)
                count_circle = count_circle + 1

        self.logger.info('SMS 监控回调:{}'.format(json.dumps(data)))
        data['payment_id'] = self.payment_id
        data['partner_id'] = self.partner_id
        data['content'] = data_post['content']
        data['callback'] = 0
        try:
            r = None
            if data['trade_type'] == 1:
                if await self.is_exits('bank_record', 'utr', data['utr']):
                    return dict(type='New', code=99, msg='UTR already exists',data=data_post)
                r = await callback.success_ds(self, data)
            elif data['trade_type'] == 2:
                r = await callback.success_df(self, data)
            elif data['trade_type'] == 3:
                r = await callback.sxf_df(self, data)
            elif data['trade_type'] == 4:
                r = await callback.cancel_df(self, data)
            # 代收回调失败额外扣除
            if r['code'] == 99 and data['trade_type'] == 1:
                ew_code = await self.create_order_code('EW')  # 额外流水号
                async with self.application.db.acquire() as conn:
                    async with conn.cursor(DictCursor) as cur:
                        if not await self.change_balance(conn, cur, 'partner', self.partner_id, -Decimal(data['amount']), ew_code, 0):
                            self.logger.warning('utr:{}Failed to deduct partner balance'.format(data['utr']))
                            await conn.rollback()
                        else:
                            data['ew_code'] = ew_code
                            data['if_ew'] = '1'
                            await conn.commit()

            if r['code'] == 100:
                data['callback'] = 1
                data['order_code'] = r['order']
            await self.create_result('bank_record', data)
            r['data'] = data_post
            r['type'] = "New"
            return r
        except Exception as e:
            data['partner_id'] = self.partner_id
            await self.create_result('bank_record', data)
            return dict(type='New', code=99, msg='Callback Error:{}'.format(e),data=data_post)

    # 断线清除
    async def clean(self):
        try:
            if self.payment_id:
                await self.qrcode_online(0)
                del phonepe_socket[int(self.payment_id)]
        except Exception:
            pass
        # if self.phone_id:
        #     await self.update_result('phonepe', {'status': 0}, {'id': self.phone_id})
        #     del phonepe_socket[int(self.phone_id)]
