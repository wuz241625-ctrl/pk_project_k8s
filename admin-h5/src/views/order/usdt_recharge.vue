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
      <el-button type="warning" plain @click="handlecopy(count.processing)">
        {{ $t('method.Msusdtczdd.buttons.processing') }}：{{ count.processing }}
      </el-button>
      <el-button type="warning" plain @click="handlecopy(count.processing_amount)">
        {{ $t('method.Msusdtczdd.buttons.processingAmount') }}：{{ count.processing_amount }}
      </el-button>
      <el-button type="primary" plain @click="handlecopy(count.amount)">
        {{ $t('method.Msusdtczdd.buttons.amount') }}：{{ count.amount }}
      </el-button>
    </el-form>
    <el-table
      :data="orderList"
      stripe
      style="width: 100%; margin-top: 30px;"
      border
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"
    >
      <el-table-column fixed="left" align="center" :label="$t('method.Msusdtczdd.columns.orderId')" width="140">
        <template slot-scope="scope">
          {{ scope.row.serial_number }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msusdtczdd.columns.partnerId')">
        <template slot-scope="scope">
          {{ scope.row.user_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msusdtczdd.txid')"  show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.txid }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msusdtczdd.columns.adminId')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msusdtczdd.columns.amount')">
        <template slot-scope="scope">
          {{ scope.row.total_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.bonusRate')">
        <template slot-scope="scope">
          {{ scope.row.bonus_rate }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.bonus')">
        <template slot-scope="scope">
          {{ scope.row.bonus }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.currencyAmount')">
        <template slot-scope="scope">
          {{ scope.row.currency_amount }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Msusdtczdd.columns.status')">
        <template slot-scope="scope">
          <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
            {{ statusType.find(item => item.id === scope.row.status).name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.usdt')">
        <template slot-scope="scope">
          {{ scope.row.usdt_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.exchangeRate')">
        <template slot-scope="scope">
          {{ scope.row.exchange_rate }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.address')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.address }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.blockChain')">
        <template slot-scope="scope">
          {{ scope.row.block_chain }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.timeCreate')" width="160">
        <template slot-scope="scope">
          {{ scope.row.created_at }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.timeSuccess')" width="160">
        <template slot-scope="scope">
          {{ scope.row.paid_at }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.timeUpdated')" width="160">
        <template slot-scope="scope">
          {{ scope.row.updated_at }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Msusdtczdd.columns.remark')" width="160">
        <template slot-scope="scope">
          {{ scope.row.remark }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" align="center" :label="$t('method.Msusdtczdd.columns.operations')" width="200px">
        <template slot-scope="scope">
          <el-button
            v-if="scope.row.status === 1"
            type="warning"
            size="small"
            @click="confirmFinishView(scope)"
          >
            {{ $t('method.Msusdtczdd.buttons.confirmFinish') }}
          </el-button>
          <el-button
            v-if="scope.row.status === -1"
            type="warning"
            size="small"
            @click="confirmFinishView(scope)"
          >
            {{ $t('method.Msusdtczdd.buttons.confirmFinish') }}
          </el-button>
          <el-button
            v-if="scope.row.status === 1"
            type="danger"
            size="small"
            @click="handleCancel(scope)"
          >
            {{ $t('method.Msusdtczdd.buttons.reject') }}
          </el-button>
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

    <el-dialog
      :title="$t('method.Msusdtczdd.dialogTitle')"
      :visible.sync="dialogTxidVisible"
      width="80%"
      :close-on-click-modal="false"
    >
      <el-form>
        <el-form-item :label="$t('method.Msusdtczdd.txidLabel')" prop="txid">
          <el-input v-model="txid" :placeholder="$t('method.Msusdtczdd.txidPlaceholder')"></el-input>
          <div v-if="txidError" class="el-form-item__error">{{ txidError }}</div>
        </el-form-item>
      </el-form>
      <span slot="footer" class="dialog-footer">
        <el-button @click="closeDialog">{{ $t('method.Msusdtczdd.buttons.cancel') }}</el-button>
        <el-button type="primary" @click="confirmFinish">{{ $t('method.Msusdtczdd.buttons.confirmFinish') }}</el-button>
      </span>
    </el-dialog>


  </div>
</template>

<script>
import {
    deepClone
} from '@/utils'
import {
    handleUsdtRechargePartner,
    getPayment, getUsdtRechargePartner
} from '@/api/recharge'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Msusdtczdd',
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
            dialogTxidVisible: false,
            serial_number: '',
            txid: '',
            txidError: '',
            amount_order: '',
            r_order: '',
            statusType: [{
                'id': 0,
                'name': this.$t('method.Msusdtczdd.statusType.0'),
                'type': 'warning'
            },
            {
                'id': 1,
                'name': this.$t('method.Msusdtczdd.statusType.1'),
                'type': 'warning'
            },
            {
                'id': 2,
                'name': this.$t('method.Msusdtczdd.statusType.2'),
                'type': 'success'
            },
            {
                'id': -1,
                'name': this.$t('method.Msusdtczdd.statusType.-1'),
                'type': 'info'
            }
            ],
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
        { label: this.$t('method.Msusdtczdd.form.serial_number'), type: 'input', param: 'serial_number' },
        {
          label: this.$t('method.Msusdtczdd.form.status'),
          type: 'select',
          selectOptions: [
            { value: 0, label: this.$t('method.Msusdtczdd.statusType.0') },
            { value: 1, label: this.$t('method.Msusdtczdd.statusType.1') },
            { value: 2, label: this.$t('method.Msusdtczdd.statusType.2') },
            { value: -1, label: this.$t('method.Msusdtczdd.statusType.-1') }
          ],
          param: 'status'
        },
        { label: this.$t('method.Msusdtczdd.form.user_id'), type: 'input', param: 'user_id' },
        { label: this.$t('method.Msusdtczdd.form.admin_id'), type: 'input', param: 'admin_id' },
        { label: this.$t('method.Msusdtczdd.form.total_amount'), type: 'input', param: 'total_amount' },
        { label: this.$t('method.Msusdtczdd.form.usdt_amount'), type: 'input', param: 'usdt_amount' },
        { label: this.$t('method.Msusdtczdd.form.top_partner_id'), type: 'input', param: 'top_partner_id' },
        { label: this.$t('method.Msusdtczdd.form.created_at'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'created_at' },
        { label: this.$t('method.Msusdtczdd.form.paid_at'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'paid_at' },
        { label: this.$t('method.Msusdtczdd.txid'), type: 'input', param: 'txid' }
      ],
      params: {},
      exportData: {
        tHeader: [
          this.$t('Mstxdd.export.serial_number'),
          this.$t('Mstxdd.export.user_id'),
          this.$t('Mstxdd.export.admin_id'),
          this.$t('Mstxdd.export.total_amount'),
          this.$t('Mstxdd.export.status'),
          this.$t('Mstxdd.export.bonus_rate'),
          this.$t('Mstxdd.export.bonus'),
          this.$t('Mstxdd.export.currency_amount'),
          this.$t('Mstxdd.export.usdt_amount'),
          this.$t('Mstxdd.export.exchange_rate'),
          this.$t('Mstxdd.export.address'),
          this.$t('Mstxdd.export.block_chain'),
          this.$t('Mstxdd.export.created_at'),
          this.$t('Mstxdd.export.paid_at'),
          this.$t('Mstxdd.export.updated_at'),
          this.$t('method.Msusdtczdd.txid')
        ],
        filterVal: [
          'serial_number', 'user_id', 'admin_id', 'total_amount', 'status', 'bonus_rate', 
          'bonus', 'currency_amount', 'usdt_amount', 'exchange_rate', 'address', 'block_chain',
          'created_at', 'paid_at', 'updated_at', 'txid'
        ],
        list: [],
        filename: this.$t('Mstxdd.export.filename')
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
        closeDialog() {
          this.dialogTxidVisible = false;
        },
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
            const res = await getUsdtRechargePartner(data)
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
    confirmFinishView({ $index, row }) {
      this.txid = ''
      this.txidError = ''
      this.dialogTxidVisible = true
      this.serial_number = row.serial_number
    },
    /* 确认收款 */
    async confirmFinish({ $index, row }) {
      const data = {
          'serial_number': this.serial_number,
          'status': 2,
          'txid': this.txid
      };
      try {
          await handleUsdtRechargePartner(data);
          this.dialogTxidVisible = false;
          this.$message({
              type: 'success',
              message: this.$t('method.payment_success')
          });
          this.getData();
      } catch (e) {
          this.txidError = e.message || this.$t('method.payment_failed');
      }
    },
    /* 驳回 */
    async handleCancel({ $index, row }) {
        this.$confirm(this.$t('method.reject_confirm'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'serial_number': row.serial_number,
                'status': -1,
                'txid': ''
            }
            try {
                await handleUsdtRechargePartner(data)
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
