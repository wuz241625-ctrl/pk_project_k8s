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
      <el-button type="success" plain @click="handlecopy(count.successOrder)">
        {{ $t('ds.table.success', { count: count.successOrder }) }}
      </el-button>
      <el-button type="danger" plain @click="handlecopy(count.failOrder)">
        {{ $t('ds.table.failure', { count: count.failOrder }) }}
      </el-button>
      <el-button type="primary" plain @click="handlecopy(getRate())">
        {{ $t('ds.table.successRate', { rate: getRate() }) }}
      </el-button>
      <el-button type="warning" plain @click="handlecopy(count.processing)">
        {{ $t('ds.table.processing', { count: count.processing }) }}
      </el-button>
      <el-button type="warning" plain @click="handlecopy(count.processing_amount)">
        {{ $t('ds.table.processingAmount', { amount: count.processing_amount }) }}
      </el-button>
      <el-button type="primary" plain @click="handlecopy(count.amount)">
        {{ $t('ds.table.totalAmount', { amount: count.amount }) }}
      </el-button>
    </el-form>
    <el-table
      :data="orderList"
      stripe
      style="width: 100%; margin-top: 30px;"
      border
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"
    >
      <el-table-column align="center" :label="$t('ds.table.orderNumber')" width="200">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.merchantNumber')" width="300" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.merchant_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.orderAmount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.status')">
        <template slot-scope="scope">
          <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
            {{ $t(`ds.status.${scope.row.status}`) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.gatewayNumber')">
        <template slot-scope="scope">
          {{ scope.row.channel_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.upi')" :show-overflow-tooltip="true" :formatter="formatText"
                       style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
        <template slot-scope="scope">
          {{ scope.row.upi }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.utr')">
        <template slot-scope="scope" v-if="scope.row.status === 4">
          {{ scope.row.utr }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.settlementAmount')">
        <template slot-scope="scope">
          {{ scope.row.realpay }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.fee')">
        <template slot-scope="scope">
          {{ scope.row.poundage }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.orderTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ds.table.successTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_updated }}
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
  </div>
</template>

<script>
import {
    getOrderds
} from '@/api/order'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    data() {
        return {
            params: {},
            orderList: [], // 数据表
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
        { labelKey: 'ds.search.orderNumber', type: 'input', param: 'code' },
        { labelKey: 'ds.search.merchantNumber', type: 'input', param: 'merchant_code' },
        { labelKey: 'ds.search.upi', type: 'input', param: 'upi' },
        { labelKey: 'ds.search.utr', type: 'input', param: 'utr' },
        { labelKey: 'ds.search.amount', type: 'input', param: 'amount' },
        { labelKey: 'ds.search.gateway', type: 'input', param: 'channel_code' },
        { labelKey: 'ds.search.status', type: 'select', selectOptions: [], param: 'status' },
        { labelKey: 'ds.search.orderTime', type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' },
        { labelKey: 'ds.search.successTime', type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_success' },
        { labelKey: 'ds.search.merchant_id', type: 'input', param: 'merchant_id' }
      ],
      exportData: { // 导出信息
      tHeader: [
          this.$t('ds.exportData.tHeader.order_number'),
          this.$t('ds.exportData.tHeader.merchant_number'),
          this.$t('ds.exportData.tHeader.order_amount'),
          this.$t('ds.exportData.tHeader.status'),
          this.$t('ds.exportData.tHeader.gateway_number'),
          this.$t('ds.exportData.tHeader.upi'),
          this.$t('ds.exportData.tHeader.utr'),
          this.$t('ds.exportData.tHeader.order_time'),
          this.$t('ds.exportData.tHeader.success_time'),
          this.$t('ds.exportData.tHeader.settlement_amount'),
          this.$t('ds.exportData.tHeader.fee')
      ],
      filterVal: ['code', 'merchant_code', 'amount', 'status', 'channel_code', 'upi', 'utr','time_create','time_success', 'realpay', 'poundage'],
      list: [],
      filename: this.$t('ds.exportData.filename')
      },
      paginationData: { // 翻页信息
          page: 1,
          size: 10,
          total: 0
      }
    }
  },
  created() {
    this.statusType.forEach(statusType => {
      this.formItemList.find(item => item.type === 'select').selectOptions.push({
        value: statusType.id,
        label: this.$t(`ds.status.${statusType.id}`) // 使用国际化
      })
    })
    this.getData()
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
  methods: {
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
            const res = await getOrderds(data)
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
            this.$notify({
                title: this.$t('method.copySuccess'),
                type: 'success'
            })
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
      },
      formatText(row, column, cellValue, index) {
          if (!cellValue) return ''
          return cellValue.length > 5 ? cellValue.slice(0, 5) + '...' : cellValue
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
        },
        formatText(row, column, cellValue, index) {
          if (!cellValue) return ''
          return cellValue.length > 5 ? cellValue.slice(0, 5) + '...' : cellValue
        }
    }
}
</script>
