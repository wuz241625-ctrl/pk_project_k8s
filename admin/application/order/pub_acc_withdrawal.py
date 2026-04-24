from application.base import BaseHandler
import tornado
import json
from application.message import msg
import pandas as pd
import re
from datetime import datetime
import csv

class importBankWithdrawal(BaseHandler):

    def __init__(self, *args, **kwargs):
        # 后续需要解析的方法可在此添加：
        # '银行名': '解析方法',
        self.bank_handle_map = {
            'BOM BANK': self.extract_bom_data,
            'INDIAN BANK': self.extract_indian_bank_data
        }
        super().__init__(*args, **kwargs)

    @staticmethod
    async def extract_indian_bank_data(self, uploaded_name):
        """
           解析 INDIAN BANK 上传的回执 Excel 文件，返回字典列表：
           [
               {'utr': 'UTR值', 's_payment_id': '收款银行id', 'tran_date': '交易日期', 'amount': '金额'},
               ...
           ]
        """
        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        # 定义目标标题字段，全部小写（目标字段本身不含空格）
        target_fields = ["credit amount", "debit amount","description"]
        try:
            with open(file_path, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                sample = f.read(1024)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample)
                except csv.Error:
                    dialect = csv.excel
                df = pd.read_csv(f, header=None, delimiter=dialect.delimiter)

            header_row_index = None
            for i, row in df.iterrows():
                # 对当前行的每个单元格做 strip() 和 lower() 处理
                row_processed = [str(cell).strip().lower() for cell in row.values]
                # 检查当前行是否包含所有目标字段
                if all(target_field in row_processed for target_field in target_fields):
                    header_row_index = i
                    break

            if header_row_index is None:
                with open(file_path, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                    df = pd.read_csv(f, skiprows=5)
                row_processed = [str(cell).strip().lower() for cell in df.columns]
                if not all(target_field in row_processed for target_field in target_fields):
                    raise ValueError("文件中未找到包含所有指定标题字段的表头行。")
            else:
                with open(file_path, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                    df = pd.read_csv(f, header=header_row_index, delimiter=dialect.delimiter)

            self.logger.info(f"动态定位到的表头行索引：{header_row_index}")

            # 去除列名前后的空格
            df.columns = [str(c).strip() for c in df.columns]
            # 数据解析逻辑
            results = []
            for i, row in df.iterrows():
                # 获取字段值并清除左右空格
                withdrawals = str(row.get("Debit Amount", "")).strip()
                deposits = str(row.get("Credit Amount", "")).strip()
                particulars = str(row.get("Description", "")).strip()
                tran_date = str(row.get("Transaction Date", "")).strip()

                # **跳过 Date 为空的行**
                if not tran_date:
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(f"Tran_Date: {tran_date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # **格式化金额**
                withdrawals = withdrawals.replace(',', '').replace(' ', '').strip()
                deposits = deposits.replace(',', '').replace(' ', '').strip()
                try:
                    withdrawals = float(withdrawals) if withdrawals else 0
                    deposits = float(deposits) if deposits else 0
                except ValueError:
                    withdrawals = 0
                    deposits = 0
                self.logger.info(f"处理后的金额数据: Withdrawals: {withdrawals}, Deposits: {deposits}")
                # **跳过无金额交易**
                if withdrawals == 0:
                    self.logger.info("该行无有效支出，跳过")
                    continue
                utr = ""
                s_payment_id = 0

                utr_pattern = r'\d+'
                particulars_l = particulars.split('/')
                if particulars_l[0].strip() == "WITHDRAWAL TRANSFER NEFT":
                    utr = particulars_l[2].strip()
                    match = re.search(utr_pattern, particulars_l[3].strip())
                    if match:
                        s_payment_id = match.group()
                elif particulars_l[0].strip() == "WITHDRAWAL TRANSFER":
                    if particulars_l[1].strip() == "IMPS":
                        utr = particulars_l[3].strip()
                        match = re.search(utr_pattern, particulars_l[len(particulars_l) - 1].strip())
                        if match:
                            s_payment_id = match.group()
                    else:
                        utr = f"CHARGES-{particulars_l[2].strip()}"

                if not utr:
                    self.logger.info("没有取到utr，跳过")
                    continue

                results.append(
                    {
                        'utr': utr,
                        's_payment_id': s_payment_id,
                        'tran_date': tran_date,
                        'amount': withdrawals,
                    }
                )
            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results
        except Exception as e:
            self.logger.info(f"读取文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_bom_data(self, uploaded_name):
        """
        解析 BOM BANK 上传的回执 Excel 文件，返回字典列表：
        [
            {'utr': 'UTR值', 's_payment_id': '收款银行id', 'tran_date': '交易日期', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **JK Bank 对应的表头**
        date_field = 'Date'  # 交易日期
        particulars_field = 'Particulars'  # 交易备注
        withdrawals_field = 'Debit'  # 支出金额
        deposits_field = 'Credit'  # 存入金额
        type_field = 'Type'  # 交易类型

        # 目标表头列表
        header_fields = [date_field, type_field, particulars_field, withdrawals_field, deposits_field]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # **查找表头行索引**
        header_row_index = None
        for i, row in df.iterrows():
            if all(field in row.astype(str).values for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 数据（跳过标题行）
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info("表头字段：", list(data.columns))

            results = []

            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(particulars_field, '')).strip()
                withdrawals = str(row.get(withdrawals_field, '')).strip()
                deposits = str(row.get(deposits_field, '')).strip()
                tran_type = str(row.get(type_field, '')).strip()
                utr = ""
                s_payment_id = 0

                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                if tran_type == 'Charges':
                    self.logger.info(f"第 {i} 行 交易类型 为Charges，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # **格式化金额**
                withdrawals = withdrawals.replace(',', '').replace(' ', '').strip()
                deposits = deposits.replace(',', '').replace(' ', '').strip()
                try:
                    withdrawals = float(withdrawals) if withdrawals else 0
                    deposits = float(deposits) if deposits else 0
                except ValueError:
                    withdrawals = 0
                    deposits = 0
                self.logger.info(f"处理后的金额数据: Withdrawals: {withdrawals}, Deposits: {deposits}")
                # **跳过无金额交易**
                if withdrawals == 0:
                    self.logger.info("该行无有效支出，跳过")
                    continue

                utr_pattern = r'\d+'
                match = re.findall(utr_pattern, particulars)

                date_list = re.findall(utr_pattern, date)
                withdrawals_list = re.findall(utr_pattern, str(withdrawals))
                suffix = "-".join(["".join(date_list),"".join(withdrawals_list)])

                if tran_type == 'IB':
                    if match and len(match) > 1:
                        utr = match[1] if match else ''
                        if utr:
                            utr = f"{utr}-{suffix}"
                        s_payment_id = match[0] if match else ''
                    elif match and len(match) == 1:
                        utr = match[0] if match else ''
                        if utr:
                            utr = f"{utr}-{suffix}"
                elif tran_type == 'IMPS':
                    if match and len(match) > 2:
                        utr = match[1] if match else ''
                        if utr:
                            utr = f"{utr}-{suffix}"
                        s_payment_id = match[len(match)-1] if match else ''
                    elif match and len(match) > 1:
                        utr = match[1] if match else ''
                        if utr:
                            utr = f"{utr}-{suffix}"
                if not utr:
                    self.logger.info("没有取到utr，跳过")
                    continue

                results.append(
                    {
                        'utr': utr,
                        's_payment_id': s_payment_id,
                        'tran_date': date,
                        'amount': withdrawals,
                    }
                )

            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")

            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            filename = data.get('filename')
            payment_id = data.get('payment_id')
            random_code = data.get('random_code')
            # 锁
            busy_key = 'import_bank_withdrawal_{}'.format(self.current_user['id'])
            if not await self.redis.setnx(busy_key, 1):
                self.logger.error('用户导入请求过于频繁，,user_id:{user_id}'.format(user_id=self.current_user['id']))
                return await self.json_response(data=msg[10010])
            await self.redis.expire(busy_key, 10)
            if await self.is_null(data, ['payment_id', 'filename']):
                self.logger.error('请求参数缺失字段,data:{data}'.format(data=data))
                return await self.json_response(data=msg[10004])
            name, file_format = filename.rsplit('.', 1)
            uploaded_file_name = '{}_{}.{}'.format(name, random_code, file_format)

            # 通过payment_id查询码商id
            payment = await self.get_result_by_condition('payment', ['partner_id'], {'id': payment_id})
            if await self.is_null(payment, ['partner_id']):
                self.logger.error('payment中缺失"partner_id"字段,请检查payment信息,payment_id:{payment_id}'.format(payment_id=payment_id))
                return await self.json_response(data=msg[10004])

            bank_sql = 'select bank.id,bank.name from bank_type bank left join payment p on p.bank_type_id = bank.id where p.id = {payment_id} limit 1'.format(payment_id=payment_id)
            bank_type_results = await self.query(bank_sql)
            if len(bank_type_results) == 0:
                self.logger.error('无法找到payment的所属银行信息,请检查payment信息,payment_id:{payment_id}'.format(payment_id=payment_id))
                return await self.json_response(data=msg[10004])

            bank_type = bank_type_results[0]
            if bank_type:
                bank_name = bank_type.get('name')
                # 调用解析方法
                handle_file_func = self.bank_handle_map.get(bank_name)
                if handle_file_func:
                    results = await handle_file_func(self, uploaded_file_name)
                    # 打印记录数
                    self.logger.info(f"Number of results processed: {len(results)}")
                    # 打印详细记录
                    self.logger.info(f"Results: {results}")
                else:
                    self.logger.error('此银行没有添加解析批量上传回执的方法： {}'.format(bank_name))
                    return await self.json_response(msg[10007])
            else:
                return await self.json_response(data=msg[10004])

            # 增加导入数据过滤，(导入数据的顺序是按时间正序排序，仅导入最新数据之后的数据)
            # 查询最新的 bank_withdrawal 记录
            last_bank_withdrawal_sql = f'select * from bank_withdrawal where payment_id={payment_id} order by id desc limit 1'.format( payment_id=payment_id)
            self.logger.info(f"查询最新 bank_withdrawal 记录: {last_bank_withdrawal_sql}")

            bank_withdrawal_results = await self.query(last_bank_withdrawal_sql)
            self.logger.info(f"查询结果: {bank_withdrawal_results}")

            # 若存在最新记录，则从最新记录后导入，若找不到最新记录则为初次导入，不处理
            if len(bank_withdrawal_results) > 0:
                last_bank_record = bank_withdrawal_results[0]
                last_bank_record_utr = last_bank_record.get('utr')
                self.logger.info(f"最新 bank_record 记录的 UTR: {last_bank_record_utr}")

                # 判断本次 results 数据中是否包含最新 UTR
                is_exits_utr = any(data['utr'] == last_bank_record_utr for data in results)
                self.logger.info(f"最新 UTR 是否在本次数据中: {is_exits_utr}")

                # 判断最新utr此次是否再次导入，若是再次导入，则仅处理此utr之后的数据
                if is_exits_utr:
                    for index, data in enumerate(results):
                        if data['utr'] == last_bank_record_utr:
                            self.logger.info(f"找到匹配的最新 UTR，位置: {index}，UTR: {data['utr']}")
                            # 从最新utr的下一条数据始处理
                            results = results[index + 1:]  # 返回最新utr之后的所有数据
                            self.logger.info(f"截取最新 UTR 之后的数据，剩余待处理数据: {results}")
                            break

            for file_data in results:
                file_data['partner_id'] = payment['partner_id']
                if await self.is_exits('bank_withdrawal', 'utr', file_data['utr']):
                    self.logger.error('导入bank_withdrawal异常,utr:{utr}重复'.format(utr=file_data['utr']))
                    continue
                file_data['admin_id'] = self.current_user['id']
                file_data['payment_id'] = payment_id
                # 保存银行记录
                if not await self.create_result('bank_withdrawal', file_data):
                    self.logger.error('导入bank_withdrawal异常,创建记录失败,utr:{utr}'.format(utr=file_data['utr']))
                    continue
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10007])

        return await self.json_response(dict(code=20000, msg='导入成功'))

# 获取
class getBankWithdrawal(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])

        condition, between = await self.split_between_condition(data['serchData'], 'time_create')

        if not between:
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}

        data_r, total ,amount_list= await self.get_result('bank_withdrawal', ['*'], ['amount'], condition, between, data['size'],data['page'])
        accountSum = 0
        if amount_list:
            accountSum += sum([amount['amount'] for amount in amount_list])

        result = dict(code=20000, data=data_r, total=total,accountSum = accountSum, msg='获取成功')
        return await self.json_response(result)