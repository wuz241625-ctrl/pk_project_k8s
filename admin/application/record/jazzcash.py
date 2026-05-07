"""
JazzCash 账单查询模块
提供 JazzCash 账户列表查询和账单下载功能
"""
import base64
import hashlib
import json
import uuid
import os
import sys
import time
from datetime import datetime
from io import BytesIO

import aiohttp
import tornado
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from application.base import BaseHandler
from application.message import msg

# 添加配置路径
parent_directory = os.path.dirname(__file__)  # application/record
grandparent_directory = os.path.dirname(parent_directory)  # application
great_grandparent_directory = os.path.dirname(grandparent_directory)  # ospay2_admin
api_directory = os.path.dirname(great_grandparent_directory)  # api
sys.path.append(os.path.join(api_directory, 'ospay2_api'))

from config import get_config

# 获取配置
conf = get_config()

# JazzCash API 配置参数
JAZZCASH_API_URL = getattr(conf, 'jazzcash_api_url', 'http://34.150.42.92:84')
JAZZCASH_USER_ID = getattr(conf, 'jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
JAZZCASH_SECRET_KEY = getattr(conf, 'jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')

# 银行名称常量
BANK_NAME_JAZZCASH = 'JAZZCASH'


class getAccountList(BaseHandler):
    """根据手机号查询 JazzCash 账户信息"""
    
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            if await self.is_null(data, ['phone']):
                return await self.json_response(data=msg[10007])
            
            phone = data['phone']
            self.logger.info(f'[JazzCash] 查询账户信息，手机号: {phone}')
            
            # 1. 通过 JOIN 查询 payment 和 bank_type 信息
            bank_sql = 'select bank.id,bank.name from bank_type bank \
                            left join payment p on p.bank_type_id = bank.id \
                            where p.phone = %s limit 1'
            bank_type_results = await self.query(bank_sql, phone)
            
            if len(bank_type_results) == 0:
                self.logger.warning(f'[JazzCash] 未找到手机号 {phone} 对应的 payment 或 bank_type 记录')
                return await self.json_response(msg[10007])
            
            bank_type = bank_type_results[0]
            bank_type_id = bank_type.get('id')
            bank_name = bank_type.get('name', '').upper()
            
            # 2. 验证是否为 JazzCash 银行
            if bank_name != BANK_NAME_JAZZCASH:
                self.logger.error(f'[JazzCash] 银行类型不匹配: 期望 {BANK_NAME_JAZZCASH}, 实际 {bank_name}')
                return await self.json_response(msg[10370])
            
            self.logger.info(f'[JazzCash] 手机号 {phone} 验证通过，bank_type_id={bank_type_id}')
            
            # 3. 调用 JazzCash API - 使用 secondLogin 获取账户信息
            api_result = await self._call_jazzcash_api('secondLogin', {
                'account_id': phone
            })
            
            # 4. 处理 API 响应
            if not api_result['success']:
                self.logger.error(f'[JazzCash] API调用失败: {api_result["error"]}')
                return await self.json_response(msg[10007])
            
            bank_response = api_result['data']
            if bank_response['code'] == 423:
                # 云机正忙，返回友好提示
                self.logger.warning(f'[JazzCash] API繁忙: {bank_response.get("msg", "服务器繁忙")}')
                return await self.json_response({
                    'code': 60008,
                    'data': None,
                    'message': '服务器繁忙，请稍后再试'
                })
            elif bank_response['code'] != 200:
                self.logger.error(f'[JazzCash] API错误: {bank_response.get("msg", "未知错误")}')
                return await self.json_response(msg[10007])
            
            # 5. 格式化账户数据
            account_data = bank_response.get('data', {}).get('data', {})
            formatted_account = {
                'accno': account_data.get('msisdn', phone),
                'accountName': account_data.get('firstNameEn', ''),
                'accountNameUr': account_data.get('firstNameUr', ''),
                'accountBalance': '0.00',  # secondLogin 不返回余额
                'accountStatus': 'active' if account_data.get('level') else 'inactive',
                'IBAN': account_data.get('iban', ''),
                'accountLevel': account_data.get('level', ''),
                'accountProfile': account_data.get('customerType', ''),
                'bankTypeId': bank_type_id,
                'bankName': bank_name
            }
            
            result = dict(
                code=20000, 
                data=[formatted_account],  # 返回数组格式保持一致
                total=1,
                bankTypeId=bank_type_id,
                bankName=bank_name,
                msg='获取 JazzCash 账户信息成功'
            )
            
            self.logger.info(f'[JazzCash] 账户查询成功: {phone}')
            return await self.json_response(result)
                
        except Exception as e:
            self.logger.error(f'[JazzCash] 查询账户信息异常: {str(e)}', exc_info=True)
            return await self.json_response(msg[10007])


class queryBill(BaseHandler):
    """根据手机号查询 JazzCash 账单记录并生成 PDF"""
    
    def _generate_jazzcash_pdf(self, transactions, phone, accno, bank_name):
        """
        为 JazzCash 交易记录生成 PDF 文件
        
        Args:
            transactions: 交易记录列表
            phone: 手机号
            accno: 账户号
            bank_name: 银行名称
            
        Returns:
            str: base64 编码的 PDF 数据
        """
        buffer = BytesIO()
        
        # 创建 PDF 文档
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []
        
        # 样式
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#333333'),
            spaceAfter=30,
            alignment=1  # 居中
        )
        
        # 标题
        title = Paragraph(f"JazzCash Transaction Statement", title_style)
        elements.append(title)
        
        # 账户信息
        account_info = [
            ['Account:', accno],
            ['Phone:', phone],
            ['Bank:', bank_name],
            ['Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ]
        
        account_table = Table(account_info, colWidths=[1.5*inch, 4*inch])
        account_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(account_table)
        elements.append(Spacer(1, 0.3*inch))
        
        # 交易记录 - 采用卡片式布局显示详细信息
        if transactions and len(transactions) > 0:
            # 添加每笔交易的详细卡片
            for idx, trx in enumerate(transactions, 1):
                # 提取字段
                trans_id = trx.get('TRANS_ID', 'N/A')
                date_time = trx.get('TRX_DTTM', '')
                trx_type = trx.get('REASON_TYPE', 'N/A')
                trx_channel = trx.get('TRX_CHANNEL', 'N/A')
                
                # 金额信息
                amount_debited = trx.get('AMOUNT_DEBITED', '0')
                amount_credited = trx.get('AMOUNT_CREDITED', '0')
                fee = trx.get('FEE', '0')
                fed = trx.get('FED', '0')
                gross_amt = trx.get('GROSS_AMT', '0')
                
                # 收款人信息
                receiver_name = trx.get('RECEIVER_NAME', 'N/A')
                account_number = trx.get('ACCOUNT_NUMBER', 'N/A')
                beneficiary_msisdn = trx.get('BENEFICIARY_MSISDN', 'N/A')
                
                # 银行信息
                bank_name_trx = trx.get('bankName', 'N/A')
                bank_code = trx.get('bankCode', 'N/A')
                
                # 发起人信息
                initiator_name = trx.get('INITIATOR_NAME', 'N/A')
                initiator_msisdn = trx.get('INITIATOR_MSISDN', 'N/A')
                
                # 其他信息
                description = trx.get('DESCRIPTION', 'N/A')
                purpose_desc = trx.get('PurposeOfRemittanceDescription', trx.get('purposeOfPayment', 'N/A'))
                purpose_code = trx.get('PurposeOfRemittance', 'N/A')
                cps_reason = trx.get('CPS_REASON_TYPE', 'N/A')
                
                # 账户信息
                ac_from = trx.get('AC_FROM', 'N/A')
                ac_to = trx.get('AC_TO', 'N/A') or 'N/A'
                sender_iban = trx.get('SenderIBAN', 'N/A')
                receiver_msisdn = trx.get('ReceiverMSISDN', 'N/A')
                
                # 税费信息
                wht = trx.get('WHT', '') or '0'
                
                # 业务信息
                use_case = trx.get('useCase', 'N/A')
                flow_id = trx.get('flowId', 'N/A')
                trx_name = trx.get('trx_name', 'N/A')
                category = trx.get('category', 'N/A')
                sub_category = trx.get('subCategory', 'N/A')
                
                # 交易属性
                is_repeatable = trx.get('isRepeatable', 'N/A')
                is_refundable = trx.get('isRefundable', 'N/A')
                
                # 技术信息
                public_ip = trx.get('PUBLIC_IP:PUBLIC_PORT', 'N/A')
                
                # 公用事业信息
                utility_company = trx.get('UTILITY_COMPANY', '') or 'N/A'
                consumer_no = trx.get('CONSUMER_NO', '') or 'N/A'
                
                # 构建交易卡片数据
                card_data = [
                    # 标题行
                    [f"Transaction #{idx} - ID: {trans_id}", ''],
                    # 基本信息
                    ['Date/Time:', date_time],
                    ['Type:', f"{trx_type} ({trx_channel})"],
                    ['Description:', description],
                    ['CPS Reason:', cps_reason],
                    # 金额信息
                    ['', ''],  # 空行
                    ['Amount Details:', ''],
                    ['  Debited Amount:', f"Rs. {amount_debited}"],
                    ['  Credited Amount:', f"Rs. {amount_credited}"],
                    ['  Gross Amount:', f"Rs. {gross_amt}"],
                    ['  Transaction Fee:', f"Rs. {fee}"],
                    ['  Federal Tax (FED):', f"Rs. {fed}"],
                    ['  Withholding Tax (WHT):', f"Rs. {wht}"],
                    # 收款人信息
                    ['', ''],  # 空行
                    ['Recipient Information:', ''],
                    ['  Name:', receiver_name],
                    ['  Account Number:', account_number],
                    ['  Mobile Number:', beneficiary_msisdn],
                    ['  Receiver MSISDN:', receiver_msisdn],
                    # 银行信息
                    ['  Bank Name:', bank_name_trx],
                    ['  Bank Code:', bank_code],
                    # 发起人信息
                    ['', ''],  # 空行
                    ['Sender Information:', ''],
                    ['  Name:', initiator_name],
                    ['  Mobile Number:', initiator_msisdn],
                    ['  Sender IBAN:', sender_iban],
                    # 账户信息
                    ['', ''],  # 空行
                    ['Account Flow:', ''],
                    ['  From Account:', ac_from],
                    ['  To Account:', ac_to],
                    # 支付目的
                    ['', ''],  # 空行
                    ['Payment Purpose:', ''],
                    ['  Purpose Code:', purpose_code],
                    ['  Purpose Description:', purpose_desc],
                    # 业务信息
                    ['', ''],  # 空行
                    ['Business Information:', ''],
                    ['  Use Case:', use_case],
                    ['  Flow ID:', flow_id],
                    ['  Transaction Name:', trx_name],
                    ['  Category:', f"{category} / {sub_category}"],
                    # 交易属性
                    ['', ''],  # 空行
                    ['Transaction Properties:', ''],
                    ['  Repeatable:', is_repeatable],
                    ['  Refundable:', is_refundable],
                    # 公用事业（如果有）
                ]
                
                # 只有在有公用事业信息时才添加
                if utility_company != 'N/A' or consumer_no != 'N/A':
                    card_data.extend([
                        ['', ''],  # 空行
                        ['Utility Information:', ''],
                        ['  Company:', utility_company],
                        ['  Consumer Number:', consumer_no],
                    ])
                
                # 技术信息
                card_data.extend([
                    ['', ''],  # 空行
                    ['Technical Information:', ''],
                    ['  Public IP/Port:', public_ip],
                ])
                
                # 创建卡片表格
                card_table = Table(card_data, colWidths=[2*inch, 4.5*inch])
                
                # 查找所有分组标题行（以':'结尾且右列为空的行）
                section_header_rows = []
                for row_idx, row in enumerate(card_data):
                    if len(row) == 2 and row[0].endswith(':') and row[1] == '' and row_idx > 0:
                        section_header_rows.append(row_idx)
                
                # 构建样式列表
                style_commands = [
                    # 标题行样式
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A90E2')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 11),
                    ('SPAN', (0, 0), (-1, 0)),  # 合并标题行
                    ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('LEFTPADDING', (0, 0), (-1, 0), 10),
                    
                    # 一般数据行样式
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('TEXTCOLOR', (0, 1), (0, -1), colors.HexColor('#666666')),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 1), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                    ('LEFTPADDING', (0, 1), (-1, -1), 10),
                    
                    # 外边框
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#4A90E2')),
                ]
                
                # 为所有分组标题添加样式
                for row_idx in section_header_rows:
                    style_commands.extend([
                        ('FONTNAME', (0, row_idx), (0, row_idx), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, row_idx), (0, row_idx), 10),
                        ('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#F0F0F0')),
                        ('SPAN', (0, row_idx), (-1, row_idx)),
                        ('TOPPADDING', (0, row_idx), (-1, row_idx), 6),
                        ('BOTTOMPADDING', (0, row_idx), (-1, row_idx), 6),
                    ])
                
                card_table.setStyle(TableStyle(style_commands))
                
                elements.append(card_table)
                elements.append(Spacer(1, 0.2*inch))  # 交易之间的间距
            
            # 统计信息
            elements.append(Spacer(1, 0.3*inch))
            total_count = len(transactions)
            summary = Paragraph(
                f"<b>Total Transactions: {total_count}</b>",
                styles['Normal']
            )
            elements.append(summary)
        else:
            no_data = Paragraph("No transactions found.", styles['Normal'])
            elements.append(no_data)
        
        # 生成 PDF
        doc.build(elements)
        
        # 获取 PDF 数据并转换为 base64
        pdf_data = buffer.getvalue()
        buffer.close()
        
        return base64.b64encode(pdf_data).decode('utf-8')
    
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            if await self.is_null(data, ['phone']):
                return await self.json_response(data=msg[10007])
            
            phone = data['phone']
            accno = data.get('accno', phone)  # 如果没有提供 accno，使用 phone
            page_no = data.get('pageNo', 1)  # 支持分页参数
            
            self.logger.info(f'[JazzCash] 查询账单，手机号: {phone}, 账户号: {accno}, 页码: {page_no}')
            
            # 1. 通过 JOIN 查询 payment 和 bank_type 信息
            bank_sql = 'select bank.id,bank.name from bank_type bank \
                            left join payment p on p.bank_type_id = bank.id \
                            where p.phone = %s limit 1'
            bank_type_results = await self.query(bank_sql, phone)
            
            if len(bank_type_results) == 0:
                self.logger.warning(f'[JazzCash] 未找到手机号 {phone} 对应的 payment 或 bank_type 记录')
                return await self.json_response(msg[10007])
            
            bank_type = bank_type_results[0]
            bank_type_id = bank_type.get('id')
            bank_name = bank_type.get('name', '').upper()
            
            # 2. 验证是否为 JazzCash 银行
            if bank_name != BANK_NAME_JAZZCASH:
                self.logger.error(f'[JazzCash] 银行类型不匹配: 期望 {BANK_NAME_JAZZCASH}, 实际 {bank_name}')
                return await self.json_response(msg[10370])
            
            self.logger.info(f'[JazzCash] 手机号 {phone} 验证通过，bank_type_id={bank_type_id}')
            
            # 3. 构造 API payload
            payload = {
                'account_id': phone
            }
            
            # JazzCash queryBill 支持 pageNo 参数
            if page_no:
                payload['pageNo'] = page_no
            
            # 4. 调用 JazzCash API - queryBill
            api_result = await self._call_jazzcash_api('queryBill', payload)
            
            # 5. 处理 API 响应
            if not api_result['success']:
                self.logger.error(f'[JazzCash] API调用失败: {api_result["error"]}')
                return await self.json_response(msg[10007])
            
            bank_response = api_result['data']
            if bank_response['code'] == 423:
                # 云机正忙，返回友好提示
                self.logger.warning(f'[JazzCash] API繁忙: {bank_response.get("msg", "服务器繁忙")}')
                return await self.json_response({
                    'code': 60008,
                    'data': None,
                    'message': '服务器繁忙，请稍后再试'
                })
            elif bank_response['code'] != 200:
                self.logger.error(f'[JazzCash] API错误: {bank_response.get("msg", "未知错误")}')
                return await self.json_response(msg[10007])
            
            # 6. 获取交易记录并生成 PDF
            bill_data = bank_response.get('data', {}).get('data', [])
            
            self.logger.info(f'[JazzCash] 开始生成 PDF，共 {len(bill_data)} 条交易记录')
            
            # 生成 PDF
            pdf_base64 = self._generate_jazzcash_pdf(bill_data, phone, accno, bank_name)
            
            # 7. 返回 PDF 数据
            result_data = {
                'type': 'pdf',
                'bankName': bank_name,
                'bankTypeId': bank_type_id,
                'fileName': f'jazzcash-statement-{phone}-{datetime.now().strftime("%Y%m%d")}.pdf',
                'fileData': pdf_base64,
                'transactionReference': f'JC-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                'downloadTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'transactionCount': len(bill_data),
                'pageNo': page_no
            }
            
            result = dict(
                code=20000, 
                data=result_data, 
                msg='查询 JazzCash 账单成功'
            )
            
            self.logger.info(f'[JazzCash] PDF 生成成功，文件大小: {len(pdf_base64)} 字符')
            return await self.json_response(result)
                
        except Exception as e:
            self.logger.error(f'[JazzCash] 查询账单异常: {str(e)}', exc_info=True)
            return await self.json_response(msg[10007])
    
    async def _call_jazzcash_api(self, action, payload):
        """
        调用 JazzCash API 的通用方法
        
        Args:
            action: API 动作名称  
            payload: API 载荷数据
            
        Returns:
            dict: {'success': bool, 'data': dict, 'error': str}
        """
        try:
            request_id = str(uuid.uuid4())
            
            inner_payload = {
                "id": request_id,
                "action": action,
                "payload": payload
            }
            
            data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            
            secret_key = JAZZCASH_SECRET_KEY
            user_id = JAZZCASH_USER_ID
            api_url = JAZZCASH_API_URL
            
            if not all([secret_key, user_id, api_url]):
                self.logger.error('[JazzCash] API配置不完整')
                return {'success': False, 'error': 'JazzCash API配置不完整'}
            
            sign_string = data_b64 + secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()
            
            form_data = {
                'user_id': user_id,
                'data': data_b64,
                'sign': sign
            }
            
            self.logger.info(f'[JazzCash] 调用 API: {action}, payload: {payload}')
            
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            start_time = time.time()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_time = time.time() - start_time
                    
                    if not 200 <= response.status < 300:
                        error_msg = f'HTTP错误: {response.status}'
                        self.logger.error(f'[JazzCash] API调用失败: {error_msg}')
                        return {'success': False, 'error': error_msg}
                    
                    response_text = await response.text()
                    self.logger.info(f'[JazzCash] API原始响应: {action}, 内容: {response_text}')
                    
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        self.logger.error(f'[JazzCash] API响应解析失败: {e}, 原始内容: {response_text}')
                        return {'success': False, 'error': f'JSON解析失败: {str(e)}'}
                    
                    self.logger.info(f'[JazzCash] API响应: {action}, 耗时: {response_time:.2f}s')
                    
                    return {
                        'success': True,
                        'data': result,
                        'error': None
                    }
                
        except aiohttp.ClientError as e:
            error_msg = f"网络请求异常: {str(e)}"
            self.logger.error(f'[JazzCash] API网络异常: {error_msg}')
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"调用API异常: {str(e)}"
            self.logger.error(f'[JazzCash] API异常: {error_msg}')
            return {'success': False, 'error': error_msg}


# 为 getAccountList 类共享 queryBill 的 _call_jazzcash_api 方法
getAccountList._call_jazzcash_api = queryBill._call_jazzcash_api
