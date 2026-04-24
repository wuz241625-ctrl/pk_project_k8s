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
      <el-button type="primary" plain @click="insertStaticsView()">添加</el-button>
    </el-form>

    <el-table
      :data="orderList"
      stripe
      style="width: 100%;margin-top:30px;"
      border @sort-change="sort_change"
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"
    >
      <el-table-column fixed="left" align="center" label="日期" sortable>
        <template slot-scope="scope">
          {{ scope.row.formatted_date }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="推广人员ID" width="240" sortable>
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="推广人员" width="240" sortable>
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="代付人数" sortable>
        <template slot-scope="scope">
          {{ scope.row.payoutCount }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="代付金额" sortable>
        <template slot-scope="scope">
          {{ scope.row.payoutSum }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="USDT人数" sortable>
        <template slot-scope="scope">
          {{ scope.row.usdtCount }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="USDT金额" sortable>
        <template slot-scope="scope">
          {{ scope.row.usdtSum }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="总计人数" sortable>
        <template slot-scope="scope">
          {{ scope.row.count }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" label="总计金额" sortable>
        <template slot-scope="scope">
          {{ scope.row.sum }}
        </template>
      </el-table-column>

      <el-table-column fixed="right" align="center" :label="$t('method.ds.orderManagement.table.operation')" width="120">
        <template slot-scope="scope">
          <el-button type="danger" size="small" @click="deleteData(scope.row.id, scope.row.partner_id)" style="margin-top:10px;">删除</el-button>
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

    
  <el-dialog :visible.sync="dialogVisibleAdd" title="添加报表数据" :close-on-click-modal="false" :style="{ width: '150%', left: '-15%' }">
    <el-form label-width="115px" label-position="left">
        <el-form-item label="码商ID数据"  class="form-item">
            <el-input
              v-model="addIds"
              type="textarea"
              placeholder="码商ID数据, 逗号分割"
              clearable
              :disabled="isDisabled"
              :autosize="{ minRows: 3, maxRows: 6 }"
              style="width: 100%;"
            />
        </el-form-item>
      
    </el-form>

    <div style="text-align:right;">
      <el-button type="primary" @click="dialogVisibleAdd=false">{{ $t('method.Mslb.buttons.cancel') }}</el-button>
      <el-button type="danger" @click="insertStatics()">{{ $t('method.Mslb.buttons.confirm') }}</el-button>
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
    getPayment,
    getStaticsReport,
    addStaticsReport,
    deleteStaticsReport
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
            isDisabled: false,
            dialogVisibleAdd: false,
            addIds: [],
            orderList: [], // 数据表
            order_field: 'id',
            sort: 'desc',
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
        { label: this.$t('method.Msczdd.form.partner_id'), type: 'input', param: 'id' },
        { label: this.$t('method.Msczdd.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'formatted_date' }
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
          '日期', // 日期
          '推广人员ID', // 推广人员ID
          '推广人员', // 推广人员
          '代付人数', // 代付人数
          '代付金额', // 代付金额
          'USDT人数', // USDT人数
          'USDT金额', // USDT金额
          '总计人数', // 总计人数
          '总计金额' // 总计人数
        ],
        filterVal: [
          'formatted_date', // 日期
          'partner_id',  // 推广人员ID
          'name',  // 推广人员
          'payoutCount', // 代付人数
          'payoutSum', // 代付金额
          'usdtCount', // USDT人数
          'usdtSum', // USDT金额
          'count', // 金额总计
          'sum', // 人数总计（USDT和代付不重复）
        ],
        list: [],  // 数据列表
        filename: '统计报表' // 设置导出文件名，可以修改为其他名称
      },
      paginationData: { // 翻页信息
          page: 1,
          size: 10,
          total: 200
      },
      columnList: [
      { name: '推广人员ID', key: 'id' },
      { name: '日期', key: 'formatted_date' },
      { name: '推广人员', key: 'name' },
      { name: '代付人数', key: 'payoutCount' },
      { name: '代付金额', key: 'payoutSum' },
      { name: 'USDT人数', key: 'usdtCount' },
      { name: 'USDT金额', key: 'usdtSum' },
      { name: '总计金额', key: 'sum' },
      { name: '总计人数', key: 'count' }
    ]
      }
    },
    created() {
        this.getData()
    },
    methods: {
      async insertStaticsView() {
          this.dialogVisibleAdd = true
      },
      /* 编辑码商*/
      async insertStatics() {
          try {
              // 正则表达式：确保输入是逗号分隔的 **纯整数**
              const idPattern = /^\s*\d+\s*(,\s*\d+\s*)*$/;
              
              if (!idPattern.test(this.addIds)) {
                  this.$message({
                      type: 'error',
                      message: '请输入正确的 ID 格式，仅支持逗号分隔的整数，例如：11,22 或 11, 22, 33'
                  });
                  return;
              }

                await addStaticsReport({
                    'id': this.addIds,
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: '添加成功'
            })
            
            this.dialogVisibleAdd = false
            this.getData()
        },
        
      /* 编辑码商*/
      async deleteData(id, partner_id) {
          try {
                await deleteStaticsReport({
                    'id': id,
                    'partner_id': partner_id,
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: '删除成功'
            })
            this.getData()
        },
        

        /* 排序*/
        async sort_change({ column }) {
            console.log(column, this.columnList)
            this.order_field = this.columnList.find(item => item.name === column.label).key
            if (column.order === 'ascending') {
                this.sort = 'asc'
            } else if (column.order === 'descending') {
                this.sort = 'desc'
            } else {
                this.order_field = 'id'
                this.sort = 'desc'
            }
            this.getData()
        },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
                this.paginationData.size = 10
            }
            // var data = {
            //     'serchData': this.params
            // }
            var data = {
                    order_field: this.order_field,
                    sort: this.sort,
                    serchData: this.params
                }
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            const res = await getStaticsReport(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.orderList = res.data
                this.count = res.count
                this.paginationData.total = res.total
                this.addIds = res.addIds
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
