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
      <el-button type="warning" plain @click="handlecopy(count.processing)">{{ $t('method.Shtxdd.processing') }}：{{ count.processing }}</el-button>
      <el-button type="primary" plain @click="handlecopy(count.amount)">{{ $t('method.Shtxdd.amount') }}：{{ count.amount }}</el-button>

    </el-form>
    <el-table
      :data="orderList"
      stripe
      style="width: 100%;margin-top:30px;"
      border
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column fixed="left" align="center" :label="$t('method.Shtxdd.orderNumber')" width="240">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shtxdd.form.merchant_id')">

        <template slot-scope="scope">
          {{ scope.row.merchant_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shtxdd.orderAmount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shtxdd.status')">
        <template slot-scope="scope">
          <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
            {{ statusType.find(item => item.id === scope.row.status).name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shtxdd.address')" width="200px">
        <template slot-scope="scope">
          {{ scope.row.address }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shtxdd.orderTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shtxdd.successTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_success }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" align="center" :label="$t('method.Shtxdd.action')" width="300px">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handlecopy(scope.row.address)">{{ $t('method.Shtxdd.copyAddress') }}</el-button>
          <el-button
            v-if="scope.row.status == 0"
            type="warning"
            size="small"
            @click="confirmFinish(scope)"
          >{{ $t('method.Shtxdd.confirmComplete') }}</el-button>
          <el-button
            v-if="scope.row.status == 0"
            type="danger"
            size="small"
            @click="handleCancel(scope)"
          >{{ $t('method.Shtxdd.reject') }}</el-button>
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
    getWithdrawMerchant,
    handleWithdrawMerchant
} from '@/api/recharge'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Mstxdd',
    data() {
        return {
            orderList: [], // 数据表
            order: '',
            dialogVisible: false,
            amount_order: '',
            statusType: [{
                'id': 0,
                'name': this.$t('method.Shtxdd.form.statusType.0'),
                'type': 'warning'
            },
            {
                'id': 1,
                'name': this.$t('method.Shtxdd.form.statusType.1'),
                'type': 'warning'
            },
            {
                'id': 2,
                'name': this.$t('method.Shtxdd.form.statusType.2'),
                'type': 'success'
            },
            {
                'id': -1,
                'name': this.$t('method.Shtxdd.form.statusType.-1'),
                'type': 'info'
            }
            ],
            count: {},
             formItemList: [
        { label: this.$t('method.Shtxdd.form.code'), type: 'input', param: 'code' },
        {
          label: this.$t('method.Shtxdd.form.status'),
          type: 'select',
          selectOptions: [
            { value: 0, label: this.$t('method.Shtxdd.statusType.0') },
            { value: 1, label: this.$t('method.Shtxdd.statusType.1') },
            { value: 2, label: this.$t('method.Shtxdd.statusType.2') },
            { value: -1, label: this.$t('method.Shtxdd.statusType.-1') }
          ],
          param: 'status'
        },
        { label: this.$t('method.Shtxdd.form.merchant_id'), type: 'input', param: 'merchant_id' },
        { label: this.$t('method.Shtxdd.form.amount'), type: 'input', param: 'amount' },
        { label: this.$t('method.Shtxdd.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' },
        { label: this.$t('method.Shtxdd.form.time_success'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_success' }
      ],
      params: {},
      exportData: {
        tHeader: [
          this.$t('method.Shtxdd.export.code'),
          this.$t('method.Shtxdd.export.merchant_id'),
          this.$t('method.Shtxdd.export.amount'),
          this.$t('method.Shtxdd.export.status'),
          this.$t('method.Shtxdd.export.address'),
          this.$t('method.Shtxdd.export.time_create'),
          this.$t('method.Shtxdd.export.payment_codes')
        ],
        filterVal: [
          'code', 'merchant_id', 'amount', 'status','address','time_create', 'time_success'
        ],
        list: [],
        filename: this.$t('method.Shtxdd.export.filename')
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
            const res = await getWithdrawMerchant(data)
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
        /* 点击复制 */
    handlecopy(amount) {
        console.log(amount)
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
    /* 完成 */
    confirmFinish({ $index, row }) {
        this.$confirm(this.$t('method.confirm_payment'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'code': row.code,
                'status': 2
            }
            try {
                await handleWithdrawMerchant(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.payment_success')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 驳回 */
    async handleCancel({ $index, row }) {
        this.$confirm(this.$t('method.reject_confirm'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'code': row.code,
                'status': -1
            }
            try {
                await handleWithdrawMerchant(data)
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
        }
    }
}
</script>
<style lang="scss" scoped>
    .el-button {
        margin: 3px;
    }
</style>
