# AU银行内容解析
import re
from decimal import Decimal
import re


async def au(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:6] == 'UPI/CR':
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            data['code'] = contents[6][:5]
        # 转出(UPI/IMPS)
        elif content[:7] == 'UPI/DR/' or content[:5] == 'IMPS-' or 'Money Transfer Dr' in content:
            data['trade_type'] = 2
            if 'UPI' in content:
                contents = content.split('/')
                data['utr'] = contents[2]
                data['ifsc'] = contents[4]
                data['code'] = contents[5][-4:]
            elif 'IMPS' in content:
                contents = content.split('-')
                data['utr'] = contents[1]
                data['ifsc'] = contents[2][:4]
                data['code'] = contents[3][-4:]
            # else:
            #     contents = content.split('-')
            #     data['utr'] = contents[1].strip(' ')
        # 退回(UPI/IMPS)
        elif content[:10] == 'UPI/DR-REV' or 'RETURN IMPS' in content:
            data['trade_type'] = 3
            if 'UPI' in content:
                contents = content.split('/')
                data['utr'] = contents[2]
                data['ifsc'] = contents[4]
                data['code'] = contents[5]
            else:
                contents = content.split('-')
                data['utr'] = contents[1]
                data['ifsc'] = contents[3]
                data['code'] = contents[4]
        # 手续费
        elif 'IMPS OUTWARD CHARGE' in content:
            data['trade_type'] = 4
        return data
    except Exception:
        return False


# kotak银行内容解析
async def kotak(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            data['code'] = contents[3][:5]
        # 转出(UPI/IMPS/Transfer)
        elif content[:3] == 'UPI' and amount < Decimal(0) or content[:8] == 'SentIMPS' or content[:7] == 'IB:SENT':
            data['trade_type'] = 2
            if 'UPI' in content:
                data['utr'] = content.split('/')[2]
            elif content[:8] == 'SentIMPS':
                contents = content.split('/')
                data['utr'] = contents[0]
                data['ifsc'] = contents[1][:(len(content[1]) - 4)]
                data['code'] = contents[1][-4:]
            else:
                data['utr'] = content.split(' ')[2]
        # 退回(UPI/IMPS)
        elif content[:3] == 'REV':
            data['trade_type'] = 3
            if 'UPI' in content:
                contents = content.split('/')
                data['utr'] = contents[2]
            else:
                contents = content.split(' ')
                data['utr'] = contents[3]
            record = await self.get_result_by_condition('bank_record', ['code', 'ifsc'],
                                                        {'trade_type': 1, 'utr': data['utr']})
            data['code'] = record['code']
            data['ifsc'] = record['ifsc']
        # 手续费
        elif content[:4] == 'Chrg':
            data['trade_type'] = 4
            contents = content.split(' ')
            data['utr'] = contents[len(contents) - 1]
        return data
    except Exception:
        return False


# idfc银行内容解析
async def idfcBak(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'Upi' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            data['code'] = contents[3][:5]
        # 转出(UPI/IMPS/Transfer)
        elif content[:3] == 'UPI' and amount < Decimal(0) or content[:8] == 'SentIMPS' or content[:7] == 'IB:SENT':
            data['trade_type'] = 2
            if 'UPI' in content:
                data['utr'] = content.split('/')[2]
            elif 'IMPS' in content:
                contents = content.split('/')
                data['utr'] = contents[0]
                data['ifsc'] = contents[1][:(len(content[1]) - 4)]
                data['code'] = contents[1][-4:]
            else:
                data['utr'] = content.split('-')[2]
        # 退回(UPI/IMPS)
        elif content[:7] == 'REV-UPI' or content[:3] == 'REV':
            data['trade_type'] = 3
            if 'UPI' in content:
                contents = content.split('/')
                data['utr'] = contents[2]
            else:
                contents = content.split(' ')
                data['utr'] = contents[3]
            record = await self.get_result_by_condition('bank_record', ['code', 'ifsc'],
                                                        {'trade_type': 1, 'utr': data['utr']})
            data['code'] = record['code']
            data['ifsc'] = record['ifsc']
        # 手续费
        elif content[:4] == 'Chrg':
            data['trade_type'] = 4
            contents = content.split(' ')
            data['utr'] = contents[len(contents) - 1]
        return data
    except Exception:
        return False


# rbl银行内容解析
async def rbl(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            data['code'] = contents[2][:5]
        # # 转出(UPI/IMPS/Transfer)
        # elif content[:3] == 'UPI' and amount < Decimal(0) or content[:8] == 'SentIMPS' or content[:7] == 'IB:SENT':
        #     data['trade_type'] = 1
        #     if 'UPI' in content:
        #         data['utr'] = content.split('/')[2]
        #     elif 'IMPS' in content:
        #         contents = content.split('/')
        #         data['utr'] = contents[0]
        #         data['ifsc'] = contents[1][:(len(content[1]) - 4)]
        #         data['code'] = contents[1][-4:]
        #     else:
        #         data['utr'] = content.split('-')[2]
        # # 手续费
        # elif content[:4] == 'Chrg':
        #     data['trade_type'] = 2
        #     contents = content.split(' ')
        #     data['utr'] = contents[len(contents) - 1]
        # # 退回(UPI/IMPS)
        # elif content[:7] == 'REV-UPI' or content[:3] == 'REV':
        #     data['trade_type'] = 3
        #     if 'UPI' in content:
        #         contents = content.split('/')
        #         data['utr'] = contents[2]
        #     else:
        #         contents = content.split(' ')
        #         data['utr'] = contents[3]
        #     record = await self.get_result_by_condition('bank_record', ['code', 'ifsc'],
        #                                                 {'trade_type': 1, 'utr': data['utr']})
        #     data['code'] = record['code']
        #     data['ifsc'] = record['ifsc']
        return data
    except Exception:
        return False


# sbi银行内容解析
async def sbi(self, content, amount):
    data = dict()
    try:
        # 转入
        if 'UPI' in content and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            data['code'] = contents[6][:5]
        # # 转出(UPI/IMPS/Transfer)
        # elif content[:3] == 'UPI' and amount < Decimal(0) or content[:8] == 'SentIMPS' or content[:7] == 'IB:SENT':
        #     data['trade_type'] = 1
        #     if 'UPI' in content:
        #         data['utr'] = content.split('/')[2]
        #     elif 'IMPS' in content:
        #         contents = content.split('/')
        #         data['utr'] = contents[0]
        #         data['ifsc'] = contents[1][:(len(content[1]) - 4)]
        #         data['code'] = contents[1][-4:]
        #     else:
        #         data['utr'] = content.split('-')[2]
        # # 手续费
        # elif content[:4] == 'Chrg':
        #     data['trade_type'] = 2
        #     contents = content.split(' ')
        #     data['utr'] = contents[len(contents) - 1]
        # # 退回(UPI/IMPS)
        # elif content[:7] == 'REV-UPI' or content[:3] == 'REV':
        #     data['trade_type'] = 3
        #     if 'UPI' in content:
        #         contents = content.split('/')
        #         data['utr'] = contents[2]
        #     else:
        #         contents = content.split(' ')
        #         data['utr'] = contents[3]
        #     record = await self.get_result_by_condition('bank_record', ['code', 'ifsc'],
        #                                                 {'trade_type': 1, 'utr': data['utr']})
        #     data['code'] = record['code']
        #     data['ifsc'] = record['ifsc']
        return data
    except Exception:
        return False


# canara(缺冲正)
async def canara(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:6] == 'UPI/CR':
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            data['code'] = contents[6][:5]
        # 转出(IMPS)
        elif content[:10] == 'IB-IMPS-DR':
            data['trade_type'] = 1
            contents = content.split('/')
            data['utr'] = contents[0]
            data['ifsc'] = contents[2]
            data['code'] = contents[3][-4:]
        # # 退回(UPI/IMPS)
        # elif content[:7] == 'REV-UPI' or content[:3] == 'REV':
        #     data['trade_type'] = 3
        #     if 'UPI' in content:
        #         contents = content.split('/')
        #         data['utr'] = contents[2]
        #     else:
        #         contents = content.split(' ')
        #         data['utr'] = contents[3]
        #     record = await self.get_result_by_condition('bank_record', ['code', 'ifsc'],
        #                                                 {'trade_type': 1, 'utr': data['utr']})
        #     data['code'] = record['code']
        #     data['ifsc'] = record['ifsc']
        return data
    except Exception:
        return False


# iob(完全)
async def iob(self, content, amount):
    data = dict()
    try:
        if content[:3] == 'UPI' and 'CR' in content:
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            data['code'] = contents[5][:5]
        if content[:4] == 'IMPS' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
        return data
    except Exception:
        return False


# paytm银行内容解析
async def paytm(self, content, amount):
    data = dict()
    data['trade_type'] = 1 if amount > Decimal(0) else 2
    data['utr'] = content

# tmb银行内容解析
async def tmb(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
        return data
    except Exception:
        return False

# punjabandsind银行内容解析
async def punjabandsind(self, content, amount):
    try:
        data = dict()
        # {'amount': '20.00', 'content': 'UPI/CR/423945628557/RAMAKANTA SAMAL/IOBA/22900100'}
        if content[:0] == 'UPI' and amount > Decimal(0):
            # 设置交易类型：1为收入
            data['trade_type'] = 1
            contents = content.split('/')
            data['utr'] = contents[2]
        return data
    except Exception:
        return False

# canara(缺冲正)
async def feb(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:6] == 'UPI IN' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            if len(contents[3]) == 5:
                data['code'] = contents[3][:5]
        elif content[:7] == 'MB IMPS' and amount < Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 2
            data['utr'] = contents[2]
            data['ifsc'] = contents[3]
        return data
    except Exception:
        return False

async def south(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
        return data
    except Exception:
        return False


async def boi(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            data['code'] = contents[6][:5]
        return data
    except Exception:
        return False


async def bob(self, content, amount):
    data = dict()
    try:
        # 转入
        if amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            if len(contents) >= 6:
                data['code'] = contents[5][:5]
        return data
    except Exception:
        return False


async def equitas(self, content, amount):
    data = dict()
    try:
        # 先去掉内容前后的空白字符
        content = content.strip()
        if content[:3] == 'UPI' and isinstance(amount, Decimal) and amount > Decimal(0):
            twelve_digit_num = re.search(r'(\d{12})', content)
            if twelve_digit_num:
                # 如果找到 UTR，则提取并返回
                data['utr'] = twelve_digit_num.group(1)
                data['trade_type'] = 1  # 设置为 UPI 转账
        return data
    except Exception:
        # return {'error': str(e)}  # 返回详细错误信息
        return False

# idbi 银行内容解析
async def idbi(self, content, amount):
    data = dict()
    try:
        # 转入
        # {'content': 'UPI/424620271744/RAMAKANTA SAMAL', 'amount': '5.00'}
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
        return data
    except Exception:
        return False
    
# idfc银行内容解析
async def idfc(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            if len(contents[3]) == 5:
                data['code'] = contents[3]
        
        return data
    except Exception:
        return False

# jana银行内容解析
async def jana(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split(' ')
            data['trade_type'] = 1
            data['utr'] = contents[1]
        return data
    except Exception:
        return False
# uco银行内容解析
async def uco(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:8] == 'MPAY/UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[3]
            if len(contents) >= 7:
                if len(contents[6]) == 5:
                    data['code'] = contents[6]
        return data
    except Exception:
        return False

async def ujjivan(self, content, amount):
    data = dict()
    try:
        # 检查交易内容和金额 
        if content[:3] == 'UPI' and Decimal(amount) > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            return data
        return False
    except Exception:
        return False
    
# icici银行内容解析
async def icici(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            if len(contents[2]) == 5:
                data['code'] = contents[2]

        return data
    except Exception:
        return False

# union银行内容解析
async def union(self, content, amount):
    data = dict()
    # UPIAB/410526224927/CR/JASPREET/UCBA/ 7217360824@ib	 	-	11.00( Cr)	63.00
    try:
        contents = content.split('/')
        # 转入
        if contents[2] == 'CR' and amount > Decimal(0):
            data['trade_type'] = 1
            data['utr'] = contents[1]
        return data
    except Exception:
        return False

async def cosmos(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[1]
            if len(contents[2]) == 5:
                data['code'] = contents[2]
        return data
    except Exception:
        return False

async def dhan(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            twelve_digit_num = re.search(r'\d{12}', contents[1])
            if twelve_digit_num:
                data['utr'] = twelve_digit_num.group()
                data['trade_type'] = 1
        return data
    except Exception:
        return False

async def karnataka(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split(':')
            twelve_digit_num = re.search(r'\d{12}', contents[1])
            if twelve_digit_num:
                data['utr'] = twelve_digit_num.group()
                data['trade_type'] = 1
        return data
    except Exception:
        return False

    
# punjabandsind银行内容解析 
async def punjabandsind(self, content, amount):
    data = dict()
    try:
        # 转入
        if content[:3] == 'UPI' and amount > Decimal(0):
            contents = content.split('/')
            twelve_digit_num = re.search(r'\d{12}', contents[2])
            if twelve_digit_num:
                data['utr'] = twelve_digit_num.group()
                data['trade_type'] = 1
        return data
    except Exception:
        return False

# kvb银行内容解析 
async def kvb(self, content, amount):
    data = dict()
    try:
        if content[:3] == 'UPI' and Decimal(amount) > 0:
            contents = content.split('-')  # 使用 '-' 分割字符串
            data['trade_type'] = 1
            data['utr'] = contents[2]
            # 采集含有5个字符的尾段
            if len(contents[-1]) == 5:
                data['code'] = contents[-1]
        return data
    except Exception:
        return False
    
# cityunion银行内容解析 
async def cityunion(self, content, amount):
    data = dict()
    try:
        if 'UPI' in content and Decimal(amount) > 0:
            contents = content.split('/')  
            data['trade_type'] = 1
            data['utr'] = contents[2]  # UTR 码
        return data  # 不采集
    except Exception:
        return False
    
# sib银行内容解析 
async def sib(self, content, amount):
    data = dict()
    try:
        if content[:3] == 'UPI' and Decimal(amount) > 0:
            contents = content.split('/')  # 使用 '/' 分割字符串
            data['trade_type'] = 1
            data['utr'] = contents[2]  # 提取第3段内容作为 UTR
        return data
    except Exception:
        return False

# yono银行内容解析
# {'content': 'BY TRANSFER\nUPI/CR/428252753120/RAMAKANT/IOBA/7219836793/Cjdhr', 'amount': 5.0}
async def yono(self, content, amount):
    data = dict()
    try:
        content = content.strip()
        # 检查内容开头
        if content[:11] == 'BY TRANSFER' and amount > Decimal(0):
            # 分割内容以提取信息
            contents = content.split('/')
            data['trade_type'] = 1
            data['utr'] = contents[2]
            # 检查确认代码的长度并确保其为5位
            if len(contents) > 6:
                data['code'] = contents[6] if len(contents[6]) == 5 else None
            else:
                data['code'] = None
        return data
    except Exception:
        return False
    
# central银行内容解析
async def central(self, content, amount):
    data = dict()
    try:
        # 先去掉内容前后的空白字符
        content = content.strip()
        # 检查内容是否包含 'UPI'，并且金额大于 0
        if 'UPI' in content and isinstance(amount, Decimal) and amount > Decimal(0):
            # 使用正则表达式从内容中提取 12 位数字的 UTR
            twelve_digit_num = re.search(r'\d{12}', content)
            if twelve_digit_num:
                # 如果找到 UTR，则提取并返回
                data['utr'] = twelve_digit_num.group()
                data['trade_type'] = 1  # 设置为 UPI 转账
            # 使用正则提取 code (是'/'和'_'之间的字母和数字组合)
            match_code = re.search(r'/([A-Za-z0-9]+)_', content)
            if match_code:
                data['code'] = match_code.group(1)
            else:
                data['code'] = None  # 如果没有找到符合条件的 code，赋值为 None
        return data

    except Exception:
        return False
    
# jk银行内容解析
async def jk(self, content, amount):
    data = dict()
    try:
        # 先去掉内容前后的空白字符
        content = content.strip()
        
        # 检查内容是否包含 'UPI'，并且金额大于 0
        if content[:3] == 'UPI' and isinstance(amount, Decimal) and amount > Decimal(0):
            # 使用正则表达式从内容中提取 12 位数字的 UTR
            twelve_digit_num = re.search(r'/(\d{12})/', content)  # Adjusting to match the correct UTR format
            if twelve_digit_num:
                # 如果找到 UTR，则提取并返回
                data['utr'] = twelve_digit_num.group(1)
                data['trade_type'] = 1  # 设置为 UPI 转账
        
        return data

    except Exception:
        return False


async def auNew(self, content, amount):
    data = dict()
    try:
        # 转入
        if 'DEPOSIT UPI CR' in content:
            data['trade_type'] = 1
            contents = [line.split(':', 1)[1] for line in content.split('-') if ':' in line]
            data['utr'] = contents[0]
            data['ifsc'] = contents[2]

        return data
    except Exception:
        return False

async def kgb(self, content, amount):
    data = dict()
    try:
        # 先去掉内容前后的空白字符
        content = content.strip()
        
        # 检查内容是否包含 'UPI'，并且金额大于 0
        if content[:3] == 'UPI' and isinstance(amount, Decimal) and amount > Decimal(0):
            # 使用正则表达式从内容中提取 12 位数字的 UTR
            twelve_digit_num = re.search(r'/(\d{12})/', content)
            if twelve_digit_num:
                # 如果找到 UTR，则提取并返回
                data['utr'] = twelve_digit_num.group(1)
                data['trade_type'] = 1  # 设置为 UPI 转账
        
        return data

    except Exception as e:
        print(f"Error occurred: {e}")
        return False
    
async def indian(self, content, amount):
    data = dict()
    try:
        content = content.strip()
        # 检查关键词和金额
        # if 'UPI' in content.upper() and isinstance(amount, Decimal) and amount > Decimal(0):
        #     # 匹配格式 /12位数字/ 或者其他 UPI 常见格式
        #     match = re.search(r'/(\d{11,12})/', content)
        #     if match:
        #         data['utr'] = match.group(1)
        #         data['trade_type'] = 1
        if isinstance(amount, Decimal) and amount > Decimal(0):
            data['utr'] = content
            data['trade_type'] = 1

        return data

    except Exception as e:
        print(f"Error occurred: {e}")
        return False
