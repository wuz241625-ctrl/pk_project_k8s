<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      :form-item-list="formItemList"
      :export-data="exportData"
      @search="getData"
      @export="getData"
    />
    <el-button type="primary" @click="handleAdd">{{ $t('button.add') }}</el-button>
    <el-button type="primary" @click="handleAdds">{{ $t('button.batchAdd') }}</el-button>

    <el-form style="margin-top: 12px;">

      <el-button
        type="success"
        plain
        @click="handlecopy(count['successOrder'])"
      >{{ $t('df.table.success', { count: count.successOrder }) }}</el-button>


      <el-button type="danger" plain @click="handlecopy(count['failOrder'])">
        {{ $t('df.table.failure', { count: count.failOrder }) }}
      </el-button>
      <el-button type="primary" plain @click="handlecopy(getRate())">
        {{ $t('df.table.successRate', { rate: getRate() }) }}
      </el-button>
      <el-button type="warning" plain @click="handlecopy(count['processing'])">
        {{ $t('df.table.processing', { count: count.processing }) }}
      </el-button>
      <el-button type="warning" plain @click="handlecopy(count['processing_amount'])">
        {{ $t('df.table.processingAmount', { amount: count.processing_amount }) }}
      </el-button>
      <el-button type="primary" plain @click="handlecopy(count['amount'])">
        {{ $t('df.table.totalAmount', { amount: count.amount }) }}
      </el-button>
    </el-form>
    <el-table
      :data="orderList"
      stripe
      style="width: 100%;margin-top:30px;"
      border
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column fixed="left" align="center" :label="$t('df.table.orderNumber')" width="200">
        <template slot-scope="scope">
          {{ scope.row['code'] }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('df.table.merchantNumber')" width="300" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row['merchant_code'] }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('df.table.orderAmount')">
        <template slot-scope="scope">
          {{ scope.row['amount'] }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('df.table.status')">
        <template slot-scope="scope">
          <el-tag :type="(statusType.find(item => item['id'] === scope.row['status']) || {type: 'info'})['type']">
            {{ $t(`df.status.${scope.row['status']}`) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.ifsc')">
        <template slot-scope="scope">
          {{ scope.row['ifsc'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.gatewayNumber')" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row['payment_bank'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.paymentAccount')" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row['payment_account'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.paymentName')" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row['payment_name'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.settlementAmount')">
        <template slot-scope="scope">
          {{ scope.row['realpay'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.fee')">
        <template slot-scope="scope">
          {{ scope.row['poundage'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.utr')" show-overflow-tooltip>
        <template slot-scope="scope" v-if="scope.row.status === 4">
          {{ scope.row['utr'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.orderTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row['time_create'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.successTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row['time_success'] }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('df.table.voucher')" width="160">
        <template slot-scope="scope">
          <el-button
            v-if="scope.row['payment_img'] === 1 && scope.row['status'] !== 0"
            type="primary"
            size="mini"
            @click="handleEdit(scope.row)" style="margin-bottom: 11px;"
          >{{ $t('df.table.viewVoucher') }}</el-button>

          <el-button  v-if="scope.row.status === 4 && scope.row.utr" type="primary" size="mini" style="margin-bottom: 11px;" @click="handleReturnReceipt(scope.row)">回执</el-button>

        </template>
        </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="$t('df.dialog.title')">
      <div class="block">
        <el-image :src="'/upload/'+ order['code']+'.jpg'" fit="contain" />
      </div>
    </el-dialog>

    <!-- 代付-->
    <el-dialog :visible.sync="dialogVisible_db" :title="$t('df.dialog.singlePayment')" :close-on-click-modal="false">
      <el-form :model="order" label-width="180px" label-position="left">
        <el-form-item :label="$t('df.form.orderAmount')">
          <el-input v-model="order.amount" :placeholder="$t('df.placeholder.orderAmount')" style="max-width: 400px;" />
        </el-form-item>
        <el-form-item :label="$t('df.form.ifsc')">
          <el-select v-model="order.ifsc" :placeholder="$t('df.placeholder.ifsc')" style="max-width: 400px;" filterable>
            <el-option value="ABPAPKKA" label="Allied Bank Limited (ABPAPKKA)"></el-option>
            <el-option value="ASCMPKKA" label="Askari Commercial Bank Limited (ASCMPKKA)"></el-option>
            <el-option value="AIINPKKA" label="Al Baraka Islamic Bank Limited (AIINPKKA)"></el-option>
            <el-option value="APNAPKKA" label="Apna Microfinance Bank (APNAPKKA)"></el-option>
            <el-option value="ALFHPKKA" label="Bank AlFalah Limited (ALFHPKKA)"></el-option>
            <el-option value="BAHLPKKA" label="Bank Al Habib Limited (BAHLPKKA)"></el-option>
            <el-option value="BKIPPKKA" label="Bank Islami Pakistan Limited (BKIPPKKA)"></el-option>
            <el-option value="KHYBPKKA" label="Bank of Khyber (KHYBPKKA)"></el-option>
            <el-option value="FAYSPKKA" label="Faysal Bank Limited (FAYSPKKA)"></el-option>
            <el-option value="HABBPKKARTG" label="Habib Bank Limited HBL (HABBPKKARTG)"></el-option>
            <el-option value="MPBLPKKA" label="Habib Metropolitan Bank (MPBLPKKA)"></el-option>
            <el-option value="HUBPPKKA" label="Hubpay (HUBPPKKA)"></el-option>
            <el-option value="JSBLPKKA" label="JS Bank (JSBLPKKA)"></el-option>
            <el-option value="KHBLDFID" label="Khushhali Microfinance Bank KMBL (KHBLDFID)"></el-option>
            <el-option value="MUCBPKKKRTG" label="MCB Bank Limited (MUCBPKKKRTG)"></el-option>
            <el-option value="MEZNPKKA" label="Meezan Bank (MEZNPKKA)"></el-option>
            <el-option value="JCICPKKA" label="Mobilink Microfinance Bank (JCICPKKA)"></el-option>
            <el-option value="NBPBPKKA" label="National Bank of Pakistan (NBPBPKKA)"></el-option>
            <el-option value="NAYAPKKA" label="NayaPay (NAYAPKKA)"></el-option>
            <el-option value="RQMIPKKA" label="Raqami Islamic Digital Bank (RQMIPKKA)"></el-option>
            <el-option value="SCBLPKKA" label="Standard Chartered Bank (SCBLPKKA)"></el-option>
            <el-option value="UNILPKKARTG" label="United Bank Limited UBL (UNILPKKARTG)"></el-option>
            <el-option value="YAPPKKA" label="YAP (YAPPKKA)"></el-option>
            <el-option value="SADAPKKA" label="SadaPay (SADAPKKA)"></el-option>
            <el-option value="JazzCash" label="JazzCash (JazzCash)"></el-option>
            <el-option value="EasyPaisa" label="EasyPaisa (EasyPaisa)"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('df.form.paymentBank')">
          <el-input v-model="order.payment_bank" :placeholder="$t('df.placeholder.paymentBank')" style="max-width: 400px;" />
        </el-form-item>
        <el-form-item :label="$t('df.form.paymentAccount')">
          <el-input v-model="order.payment_account" :placeholder="$t('df.placeholder.paymentAccount')" style="max-width: 400px;" />
        </el-form-item>
        <el-form-item :label="$t('df.form.paymentName')">
          <el-input v-model="order.payment_name" :placeholder="$t('df.placeholder.paymentName')" style="max-width: 400px;" />
        </el-form-item>
        <el-form-item :label="$t('df.form.googleVerification')">
          <el-input v-model="order.google" :placeholder="$t('df.placeholder.googleVerification')" style="max-width: 400px" maxlength="6" />
        </el-form-item>
      </el-form>
      <span slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible_db = false">{{ $t('button.cancel') }}</el-button>
        <el-button type="primary" @click="confirmOrder">{{ $t('button.confirm') }}</el-button>
      </span>
    </el-dialog>

    <!-- 批量代付-->
    <el-dialog :visible.sync="dialogVisible_pl" :title="$t('df.table.batch_payment')" :close-on-click-modal="false">
      <upload-excel-component
        style="margin-left: 6px;"
        :on-success="handleSuccess"
        :before-upload="beforeUpload"
      />
      <el-table
        :data="tableData"
        style="margin-top: 20px;"
        border
        :header-cell-style="{ background:'#DCDFE6', color:'#606266'}"
        stripe
      >
        <el-table-column v-for="item of tableHeader" :key="item" :prop="item" :label="item" />
      </el-table>
      <el-input
        v-model="google"
        :placeholder="$t('df.table.enter_google_code')"
        style="max-width: 282px; margin-top: 12px;"
        maxlength="6"
      />
      <div style="text-align:right;margin-top: 12px;">
        <el-button type="primary" @click="dialogVisible_pl=false">{{ $t('button.cancel') }}</el-button>
        <el-button type="danger" @click="confirmOrders">{{ $t('button.confirm') }}</el-button>
      </div>
    </el-dialog>

    <div class="block" style="margin-top: 20px;">
      <el-pagination
        background
        :current-page="paginationData.page"
        :page-sizes="[10, 20, 50, 100]"
        :page-size="paginationData.size"
        layout="total, sizes, prev, pager, next, jumper"
        :total="paginationData.total"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>



    <!-- 回执 -->
    <el-dialog title="回执" width="600px" :visible.sync="receiptInfo.show" :close-on-click-modal="false" @close="receiptInfo.reset()">
      <div class="receipt-info">
          <div class="receipt-info-amount">(PKR){{ receiptInfo.currentInfo ? receiptInfo.currentInfo.amount : '-' }}</div>
          <div class="receipt-info-content">
              <el-row type="flex" align="middle" class="receipt-info-row">
                  <el-col :span="12">Status</el-col>
                  <el-col :span="12">{{ getReceiptStatus(receiptInfo.currentInfo ? receiptInfo.currentInfo.status : null) }}</el-col>
              </el-row>

              <div class="receipt-info-line">{{ '*'.repeat(70) }}</div>
              <el-row type="flex" class="receipt-info-row">
                  <el-col :span="12">Beneficiary name</el-col>
                  <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.payment_name : '-' }}</el-col>
              </el-row>
              <el-row type="flex" align="middle" class="receipt-info-row">
                  <el-col :span="12">A/C No</el-col>
                  <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.payment_account : '-' }}</el-col>
              </el-row>
              <el-row type="flex" align="middle" class="receipt-info-row">
                  <el-col :span="12">IFSC</el-col>
                  <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.ifsc : '-' }}</el-col>
              </el-row>
              <div class="receipt-info-line">{{ '*'.repeat(70) }}</div>
              <el-row type="flex" align="middle" class="receipt-info-row handwritten">
                  <el-col :span="12">UTR</el-col>
                  <el-col :span="12">
                      <span :class="{'empty': !receiptInfo.temporaryInformation.utr}">{{ receiptInfo.temporaryInformation.utr || 'Move mouse in to edit utr' }}</span>
                      <el-input size="small" v-model="receiptInfo.temporaryInformation.utr" placeholder="Please enter utr" />
                  </el-col>
              </el-row>
<!--              <el-row type="flex" align="middle" class="receipt-info-row handwritten">-->
<!--                  <el-col :span="12">Debit Account</el-col>-->
<!--                  <el-col :span="12">-->
<!--                      <span :class="{'empty': !receiptInfo.temporaryInformation.debitAccount}">{{ receiptInfo.temporaryInformation.debitAccount || 'Move mouse in to edit Debit Account' }}</span>-->
<!--                      <el-input size="small" v-model="receiptInfo.temporaryInformation.debitAccount" placeholder="Please enter Debit Account" />-->
<!--                  </el-col>-->
<!--              </el-row>-->
              <el-row type="flex" align="middle" class="receipt-info-row">
                  <el-col :span="12">Sent Time</el-col>
                  <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.time_success : '-' }}</el-col>
              </el-row>
          </div>
      </div>
  </el-dialog>


  </div>
</template>

<script>
import {
    deepClone
} from '@/utils'
import UploadExcelComponent from '@/components/UploadExcel/index.vue'
import {
    getOrderdf,
    addDf,
    addDfpl
} from '@/api/order'

export default {
    name: 'UploadExcel',
    components: {
        UploadExcelComponent
    },
    data() {
        return {
            params: {},
            currentId: 0,
                receiptInfo: {
                    show: false,
                    currentInfo: null,
                    reset() {
                        this.show = false
                        this.currentInfo = null
                        this.temporaryInformation = {
                            utr: '',
                            debitAccount: ''
                        }
                    },
                    temporaryInformation: {
                        utr: '',
                        debitAccount: ''
                    }
            },
            orderList: [], // 数据表
            dialogVisible: false,
            dialogVisible_db: false,
            dialogVisible_pl: false,
            isProcessing: false,
            order: {},
            en_name: {
                '金额': 'amount',
                '银行名称': 'payment_bank',
                'IFSC': 'ifsc',
                '银行账号': 'payment_account',
                '姓名': 'payment_name'
            },
            google: '',
            orders: [],
            tableData: [],
            tableHeader: [],
            statusType: [{
                'id': 0,
                'name': '派单中',
                'type': 'warning'
            },
            {
                'id': 1,
                'name': '待支付',
                'type': 'danger'
            },
            {
                'id': 2,
                'name': '待确认',
                'type': 'danger'
            },
            {
                'id': 3,
                'name': '回调中',
                'type': 'primary'
            },
            {
                'id': 4,
                'name': '已完成',
                'type': 'success'
            },
            {
                'id': -1,
                'name': '已取消',
                'type': 'info'
            },
            {
                'id': -2,
                'name': '取消中',
                'type': 'info'
            },
            {
                'id': 5,
                'name': '处理中',
                'type': 'warning'
            }
            ],
            count: {
                failOrder: 0,
                successOrder: 0,
                rate: 0,
                processing: 0,
                amount: 0
            },
            formItemList: [
              { "labelKey": "df.search.code", "type": "input", "param": "code" },
              { "labelKey": "df.search.merchant_code", "type": "input", "param": "merchant_code" },
              { "labelKey": "df.search.status", "type": "select", "selectOptions": [], "param": "status" },
              { "labelKey": "df.search.payment_name", "type": "input", "param": "payment_name" },
              { "labelKey": "df.search.payment_account", "type": "input", "param": "payment_account" },
              { "labelKey": "df.search.payment_type", "type": "input", "param": "payment_type" },
              { "labelKey": "df.search.amount", "type": "input", "param": "amount" },
              { "labelKey": "df.search.channel_code", "type": "input", "param": "channel_code" },
              { "labelKey": "df.search.time_create", "type": "dateTimePicker", "param": "time_create" },
              { "labelKey": "df.search.time_success", "type": "dateTimePicker", "param": "time_success" },
              { "labelKey": 'ds.search.merchant_id', type: 'input', param: 'merchant_id' }
            ],
            exportData: { // 导出信息
              tHeader: [
                this.$t('df.exportData.tHeader.order_number'),
                this.$t('df.exportData.tHeader.merchant_code'),
                this.$t('df.exportData.tHeader.order_amount'),
                this.$t('df.exportData.tHeader.status'),
                this.$t('df.exportData.tHeader.bank_name'),
                this.$t('df.exportData.tHeader.payment_name'),
                this.$t('df.exportData.tHeader.payment_account'),
                this.$t('df.exportData.tHeader.payment_type'),
                this.$t('df.exportData.tHeader.order_time'),
                this.$t('df.exportData.tHeader.success_time'),
                this.$t('df.exportData.tHeader.settlement_amount'),
                this.$t('df.exportData.tHeader.poundage')
              ],
              filterVal: ['code', 'merchant_code', 'amount', 'status', 'payment_bank', 'payment_name', 'payment_account', 'payment_type', 'time_create', 'time_success', 'realpay', 'poundage'],
              list: [],
              filename: this.$t('df.exportData.filename')
            },
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 0
            }
        }
    },
    computed: {
      // Compute translated labels
      translatedFormItemList() {
        return this.formItemList.map(item => ({
          ...item,
          label: this.$t(item.labelKey) // Translate the label using i18n
        }));
      }
    },
    created() {
        this.statusType.forEach(statusType => {
          this.formItemList.find(item => item.type === 'select').selectOptions.push({
            value: statusType.id,
            label: this.$t(`df.status.${statusType.id}`) // 使用国际化
          })
        })
        this.getData()
    },
    methods: {
        /** 回执 */
        handleReturnReceipt(row) {
          console.log(row)
          this.currentId = row.id
          this.receiptInfo.show = true
          this.receiptInfo.currentInfo = row
          this.receiptInfo.temporaryInformation.utr = row.utr
          this.receiptInfo.temporaryInformation.debitAccount = row.debit_account
        },
      getReceiptStatus(status) {
        switch (status) {
          case 3:
            return 'Callback'
          case 4:
            return 'Succeed'
          default:
            return '-'
        }
      },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            var data = {
                'serchData': this.params
            }
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            const res = await getOrderdf(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.orderList = res.data
                this.count = res.count
                this.paginationData.total = res.total
            }
        },
        // 计算成功率
        getRate() {
            var orders = this.count.failOrder + this.count.successOrder
            if (orders) {
                return (this.count.successOrder / orders * 100).toFixed(4) + '%'
            }
            return '0%'
        },
        // 点击复制
        handlecopy(amount) {
            const oInput = document.createElement('input')
            oInput.value = amount
            document.body.appendChild(oInput)
            oInput.select() // 选择对象;
            document.execCommand('Copy') // 执行浏览器复制命令
            this.$message({
                title: this.$t('method.copySuccess'),
                type: 'success'
            })
        },
        /* 查看凭证*/
        handleEdit(order) {
            this.dialogVisible = true
            this.checkStrictly = true
            this.order = deepClone(order)
        },
        /* 新增代付*/
        handleAdd() {
            this.isProcessing = false
            this.order = {}
            this.dialogVisible_db = true
        },
        async confirmOrder() {
            this.isProcessing = true
            var string = /[`~!@#$%^&*()_+\-=:;"'<>,.?/{\[\]}|\\.]/
            for (var i in this.order) {
                if (string.test(this.order[i])) {
                    this.isProcessing = false
                    this.$message({
                        message: this.$t('method.pleaseFillCorrectContent'),
                        type: 'warning'
                    })
                    return
                }
            }

            try {
                await addDf(this.order)
            } catch (err) {
                this.isProcessing = false
                return
            }
            this.$message({
                title: this.$t('method.submitSuccess'),
                type: 'success'
            })
            this.dialogVisible_db = false
            this.getData()
        },
        /* 新增批量代付*/
        handleAdds() {
            this.dialogVisible_pl = true
            this.tableData = []
            this.orders = []
            this.google = ''
        },
        /* 批量上传*/
        handleSuccess({
            results,
            header
        }) {
            this.tableData = results
            this.tableHeader = header
            var string = /[`~!@#$%^&*()_+\-=:;"'<>,.?/{\[\]}|\\.]/
            try {
                this.tableData.forEach(item => {
                    var order = {}
                    for (var i in item) {
                        if (string.test(item[i])) {
                            this.$message({
                                message: this.$t('method.fileIncorrect'),
                                type: 'warning'
                            })
                            this.orders = []
                            this.tableData = []
                            return false
                        }
                        // 去除空格
                        order[this.en_name[i]] = String(item[i]).replace(/(^[\s\n\t]+|[\s\n\t]+$)/g, '')
                    }
                    this.orders.push(order)
                })
            } catch (error) {
                this.tableData = []
                this.orders = []
                this.$message({
                    message: this.$t('method.fileIncorrect'),
                    type: 'warning'
                })
            }
        },
        beforeUpload(file) {
            const isLt1M = file.size / 1024 / 1024 < 1
            if (isLt1M) {
                return true
            }
            this.$message({
                message: this.$t('method.uploadFileSizeError'),
                type: 'warning'
            })
            return false
        },
        /* 批量提交*/
        async confirmOrders() {
            if (this.orders.length === 0) {
                this.$message({
                    message: this.$t('method.pleaseSelectFile'),
                    type: 'warning'
                })
            } else if (this.google === '' || this.google.length !== 6) {
                this.$message({
                    message: this.$t('method.incorrectGoogleCode'),
                    type: 'warning'
                })
            } else {
                var fail = 0
                try {
                    fail = (await addDfpl({
                        'orders': this.orders,
                        'google': this.google
                    })).data.fail
                } catch (err) {
                    return
                }
                if (fail === 0) {
                    this.$message({
                        message: this.$t('method.allSubmitSuccess'),
                        type: 'success'
                    })
                } else {
                    this.$message({
                        message: fail + this.$t('method.submitFail'),
                        type: 'warning'
                    })
                }
                this.dialogVisible_pl = false
                this.getData()
            }
        },
        // 改变分页大小
        handleSizeChange(val) {
            this.paginationData.size = val
            this.getData()
        },
        // 改变当前页
        handleCurrentChange(val) {
            this.paginationData.page = val
            this.getData()
        }
    }
}
</script>

<style scoped lang="scss">
.receipt-info {
    color: #000;
    padding: 5px 30px;
    font-weight: 500;
    .receipt-info-amount {
        text-align: center;
        font-size: 24px;
        margin-bottom: 15px;
    }
    .receipt-info-line {
        font-size: 18px;
        margin-bottom: 10px;
        margin: 5px 0;
    }
    .receipt-info-row {
        margin-bottom: 12px;
        height: 25px;
        &.handwritten {
            cursor: pointer;

            .el-input {
                display: none;
            }

            span.empty {
                color: #bbb;
                font-size: 12px;
                font-weight: 400;
            }

            &:hover {
                .el-input {
                    display: inline-block;
                }
                span {
                    display: none;
                }
            }
        }
    }
}
</style>
