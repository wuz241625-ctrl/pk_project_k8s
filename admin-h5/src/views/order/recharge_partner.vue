<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      :form-item-list="formItemList"
      :export-data="exportData"
      @search="getData"
      @export="getData"
    />
    <el-form>
      <el-button type="warning" plain @click="handlecopy(count.processing)">{{ $t('method.Msczdd.buttons.processing') }}：{{ count.processing }}</el-button>
      <el-button type="warning" plain @click="handlecopy(count.processing_amount)">{{ $t('method.Msczdd.buttons.processingAmount') }}：{{ count.processing_amount }}</el-button>
      <el-button type="primary" plain @click="handlecopy(count.amount)">{{ $t('method.Msczdd.buttons.amount') }}：{{ count.amount }}</el-button>
    </el-form>
    <el-table
      :data="orderList"
      stripe
      style="width: 100%;margin-top:30px;"
      border
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"
    >
      <el-table-column fixed="left" align="center" :label="$t('method.Msczdd.columns.orderId')" width="240">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msczdd.columns.partnerId')">
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msczdd.columns.adminId')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msczdd.columns.amount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msczdd.columns.status')">
        <template slot-scope="scope">
          <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
            {{ statusType.find(item => item.id === scope.row.status).name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.bank')" width="200px">
        <template slot-scope="scope">
          {{ scope.row.bank }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.account')" width="200px">
        <template slot-scope="scope">
          {{ scope.row.account }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.ifsc')" width="200px">
        <template slot-scope="scope">
          {{ scope.row.ifsc }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.sysPaymentId')">
        <template slot-scope="scope">
          {{ scope.row.sys_payment_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.timeCreate')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.timeSuccess')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_success }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msczdd.columns.timeUpdated')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_updated }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" align="center" :label="$t('method.Msczdd.columns.operations')" width="220px">
        <template slot-scope="scope">
          <el-button
            v-if="scope.row.status === 0"
            type="warning"
            size="small"
            @click="handlePass(scope)"
          >{{ $t('method.Msczdd.buttons.process') }}</el-button>
          <el-button
            v-if="scope.row.status === 1"
            type="warning"
            size="small"
            @click="confirmFinish(scope)"
          >{{ $t('method.Msczdd.buttons.confirmFinish') }}</el-button>
          <el-button
            v-if="scope.row.status === 1"
            type="danger"
            size="small"
            @click="handleCancel(scope)"
          >{{ $t('method.Msczdd.buttons.reject') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

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

    <el-dialog :visible.sync="dialogVisible" :title="$t('method.Msczdd.dialogs.processBinding')" :close-on-click-modal="false">
      <el-form :model="order" label-width="80px" label-position="left">
        <el-form-item :label="$t('method.Msczdd.labels.orderCode')">
          <el-input v-model="order.code" disabled />
        </el-form-item>
        <el-form-item :label="$t('method.Msczdd.labels.partnerId')">
          <el-input v-model="order.partner_id" disabled />
        </el-form-item>
        <el-form-item :label="$t('method.Msczdd.labels.amount')">
          <el-input v-model="order.amount" disabled />
        </el-form-item>
        <el-form-item :label="$t('method.Msczdd.labels.sysPayment')">
          <el-select
            v-model="order.sys_payment_id"
            v-el-select-loadmore="loadmore"
            filterable
            :filter-method="dataFilter"
            default-first-option
            :placeholder="$t('method.Msczdd.placeholders.selectSysCard')"
            @change="$forceUpdate();"
          >
            <el-option
              v-for="paymenttype in paymentType"
              :key="paymenttype.id"
              :label="`${paymenttype.bank} | ${paymenttype.name} | ${paymenttype.account} | ${paymenttype.ifsc} |`"
              :value="paymenttype.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('method.Msczdd.buttons.cancel') }}</el-button>
        <el-button type="danger" @click="confirmPass">{{ $t('method.Msczdd.buttons.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
    deepClone
} from '@/utils'
import {
    getRechargePartner,
    handleRechargePartner,
    getPayment
} from '@/api/recharge'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Msczdd',
    directives: {
        /** 下拉框懒加载 */
        'el-select-loadmore': {
            bind(el, binding) {
                const SELECTWRAP_DOM = el.querySelector(
                    '.el-select-dropdown .el-select-dropdown__wrap'
                )
                SELECTWRAP_DOM.addEventListener('scroll', function() {
                    const condition =
                            this.scrollHeight - this.scrollTop <= this.clientHeight
                    if (condition) {
                        binding.value()
                    }
                })
            }
        }
    },
    data() {
        return {
            orderList: [], // 数据表
            order: '',
            dialogVisible: false,
            amount_order: '',
            r_order: '',
            paymentType: [],
            paymentTypePage: 1,
            paymentTypePageSize: 10,
            _paymentTypeData: null,
            partner_recharge: [],
            merchant_recharge: [],
            count: {
                failOrder: 0,
                successOrder: 0,
                rate: 0,
                processing: 0,
                amount: 0
            },
            formItemList: [
        { label: this.$t('method.Msczdd.form.order_id'), type: 'input', param: 'code' },
        {
          label: this.$t('method.Msczdd.form.status'),
          type: 'select',
          selectOptions: [
            { value: 0, label: this.$t('method.Msczdd.statusType.pending') },
            { value: 1, label: this.$t('method.Msczdd.statusType.processing') },
            { value: 2, label: this.$t('method.Msczdd.statusType.completed') },
            { value: -1, label: this.$t('method.Msczdd.statusType.canceled') }
          ],
          param: 'status'
        },
        { label: this.$t('method.Msczdd.form.partner_id'), type: 'input', param: 'partner_id' },
        { label: this.$t('method.Msczdd.form.admin_id'), type: 'input', param: 'admin_id' },
        { label: this.$t('method.Msczdd.form.amount'), type: 'input', param: 'amount' },
        { label: this.$t('method.Msczdd.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' },
        { label: this.$t('method.Msczdd.form.time_success'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_success' }
      ],
      statusType: [
        { id: 0, name: 'pending', type: 'warning' },
        { id: 1, name: 'processing', type: 'warning' },
        { id: 2, name: 'completed', type: 'success' },
        { id: -1, name: 'canceled', type: 'info' }
      ],
      params: {},
      exportData: {
        tHeader: [
          this.$t('method.Msczdd.export.order_id'),
          this.$t('method.Msczdd.export.partner_id'),
          this.$t('method.Msczdd.export.admin_id'),
          this.$t('method.Msczdd.export.amount'),
          this.$t('method.Msczdd.export.status'),
          this.$t('method.Msczdd.export.account'),
          this.$t('method.Msczdd.export.name'),
          this.$t('method.Msczdd.export.sys_payment_id'),
          this.$t('method.Msczdd.export.time_create'),
          this.$t('method.Msczdd.export.time_success'),
          this.$t('method.Msczdd.export.time_updated')
        ],
        filterVal: ['code', 'partner_id', 'admin_id', 'amount', 'status', 'account', 'name', 'sys_payment_id', 'time_create', 'time_success', 'time_updated'],
        list: [],
        filename: this.$t('method.Msczdd.export.filename')
      },
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            }
        }
    },
    created() {
        this.getData()
    },
    methods: {
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
                this.paginationData.size = 10
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
            const res = await getRechargePartner(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.orderList = res.data
                this.count = res.count
                this.paginationData.total = res.total
            }
        },
        /* 点击搜索 */
        handlesearch(params) {
            this.serchData = params
            this.getData()
        },
        /* 计算成功率 */
        getRate() {
            var orders = this.count.failOrder + this.count.successOrder
            if (orders) {
                return (this.count.successOrder / orders * 100).toFixed(4) + '%'
            }
            return '0%'
        },
         /* 点击复制 */
        handlecopy(amount) {
        const oInput = document.createElement('input')
        oInput.value = amount
        document.body.appendChild(oInput)
        oInput.select() // 选择对象;
        document.execCommand('Copy') // 执行浏览器复制命令
        this.$notify({
            title: this.$t('method.copy_success'),
            type: 'success'
        })
    },
    /* 处理绑卡 */
    async handlePass(scope) {
        this.order = deepClone(scope.row)
        this.amount_order = ''
        this.r_order = ''
        this.dialogVisible = true

        this.paymentType = []
        this.paymentTypePage = 1
        this._paymentTypeData = null
        this.getPaymentTypeData()
            // var data = { 'serchData': { 'status': 0 }, 'size': 0, 'page': 0 }
            // try { this.merchant_recharge = (await getRechargeMerchant(data)).data } catch (e) { return }
            // try { this.partner_recharge = (await getRechargePartner(data)).data } catch (e) { return }
    },
    /* 确认出款 */
    async confirmPass() {
        var data = {
            'status': 1
        }
        var message = ''
        if (this.order.sys_payment_id === '') {
            message = this.$t('method.bind_card')
        }
        if (message) {
            this.$message({
                type: 'warning',
                message: message
            })
        } else {
            data.code = this.order.code
            data.sys_payment_id = this.order.sys_payment_id
            try {
                await handleRechargePartner(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.bind_success')
            })
            this.dialogVisible = false
            this.getData()
        }
    },
    /* 确认收款 */
    confirmFinish({ $index, row }) {
        this.$confirm(this.$t('method.confirm_payment_completed'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'code': row.code,
                'status': 2
            }
            try {
                await handleRechargePartner(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.withdrawal_completed')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 驳回 */
    async handleCancel({ $index, row }) {
        this.$confirm(this.$t('method.confirm_reject'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'code': row.code,
                'status': -1
            }
            try {
                await handleRechargePartner(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.reject_success')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 改变分页大小 */
    handleSizeChange(val) {
        this.paginationData.size = val
        this.getData()
    },
    /* 改变当前页 */
    handleCurrentChange(val) {
        this.paginationData.page = val
        this.getData()
    },
    // 懒加载方法
    loadmore() {
        if (this._paymentTypeData.length == 0) return
        this.paymentTypePage++
        this.getPaymentTypeData()
    },
    /** 一次加载十条 */
    async getPaymentTypeData() {
        var data = {
            'serchData': {
                'status': 1
            },
            'size': 10,
            'page': this.paymentTypePage
        }
        try {
            this._paymentTypeData = (await getPayment(data)).data
            if (this._paymentTypeData.length > 0) {
                this.paymentType = this.paymentType.concat(this._paymentTypeData)
            }
        } catch (e) {
            return
        }
    },
    /** 下拉框搜索 */
    dataFilter(val) {
        if (val) { // val存在
            this.paymentType = this.paymentType.filter((item) => {
                if (item.account.indexOf(val) !== -1) { // 这里匹配的是选项的value，也可以改成label
                    return true
                }
            })
        } else { // val为空时，还原数组
            this.paymentType = []
            this.paymentTypePage = 1
            this._paymentTypeData = null
            this.getPaymentTypeData()
        }
    }
  }
}
</script>
<style lang="scss" scoped>
    .el-button {
        margin: 3px;
    }
</style>
