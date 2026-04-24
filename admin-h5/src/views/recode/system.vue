<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" :export-data="exportData" @search="getData" @export="getData" />
    <el-form>
      <el-button type="success" plain @click="handlecopy(count.amount_out)">{{ $t('method.Stls.amount_out') }}：{{ count.amount_out }}</el-button>
      <el-button type="danger" plain @click="handlecopy(count.amount_in)">{{ $t('method.Stls.amount_in') }}：{{ count.amount_in }}</el-button>
      <el-button type="primary" plain @click="handlecopy(count.amount)">{{ $t('method.Stls.amount') }}：{{ count.amount }}</el-button>
    </el-form>
    <el-table :data="recordList" stripe style="width: 100%;margin-top:30px;" border :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('method.Stls.code')" width="260">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.record_type')">
        <template slot-scope="scope">
          {{ recordType.find(item => item.id === scope.row.record_type).name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.amount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" label="流水类型">
        <template slot-scope="scope">
          {{ recordType.find(item => item.id === scope.row.record_type).name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.account')">
        <template slot-scope="scope">
          {{ scope.row.account }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.type')">
        <template slot-scope="scope">
          {{ scope.row.type }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.time_create')" width="200">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.admin_id')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Stls.remark')">
        <template slot-scope="scope">
          {{ scope.row.remark }}
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
import { getSysRecord } from '@/api/record'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Stls',
    data() {
        return {
            recordList: [],
            count: {
                amount_out: 0,
                amount_in: 0,
                amount: 0
            },
            formItemList: [
        { label: this.$t('method.Stls.form.code'), type: 'input', param: 'code' },
        { label: this.$t('method.Stls.form.admin_id'), type: 'input', param: 'admin_id' },
        { label: this.$t('method.Stls.form.name'), type: 'input', param: 'name' },
        { label: this.$t('method.Stls.form.account'), type: 'input', param: 'account' },
        { label: this.$t('method.Stls.form.amount'), type: 'input', param: 'amount' },
        { label: this.$t('method.Stls.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' }
      ],
      params: {},
      exportData: {
        tHeader: [
          this.$t('method.Stls.export.code'),
          this.$t('method.Stls.export.record_type'),
          this.$t('method.Stls.export.amount'),
          this.$t('method.Stls.export.name'),
          this.$t('method.Stls.export.account'),
          this.$t('method.Stls.export.type'),
          this.$t('method.Stls.export.time_create'),
          this.$t('method.Stls.export.admin_id'),
          this.$t('method.Stls.export.remark')
        ],
        filterVal: [
          'code', 'record_type', 'amount', 'name', 'account', 'type', 'time_create', 'admin_id', 'remark'
        ],
        list: [],
        filename: this.$t('method.Stls.export.filename')
      },
            paginationData: {
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
            var data = { 'serchData': this.params }
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            const res = await getSysRecord(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.recordList = res.data
                this.count = res.count
                this.paginationData.total = res.total
            }
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
