<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" @search="getData" />
    <el-table
      :data="merchantList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      @sort-change="sort_change"
    >
      <el-table-column align="center" :label="$t('Shpm.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.phone')">
        <template slot-scope="scope">
          {{ scope.row.cellphone }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.balance')" sortable>
        <template slot-scope="scope">
          {{ scope.row.balance }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.count')" sortable>
        <template slot-scope="scope">
          {{ scope.row.count }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.amount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.success_count')" sortable>
        <template slot-scope="scope">
          {{ scope.row.success_count }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.success_amount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.success_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Shpm.table.rate')" sortable>
        <template slot-scope="scope">
          {{ scope.row.rate + '%' }}
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
import { getMerchantRank } from '@/api/merchant'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Shpm',
    data() {
        return {
            merchantList: [],
            order_field: '',
            sort: null,
             formItemList: [
        { label: this.$t('Shpm.form.channel_code'), type: 'input', param: 'channel_code' },
        { label: this.$t('Shpm.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' }
      ],
            params: {},
            columnList: [
        { name: this.$t('Shpm.columns.balance'), key: 'balance' },
        { name: this.$t('Shpm.columns.count'), key: 'count' },
        { name: this.$t('Shpm.columns.amount'), key: 'amount' },
        { name: this.$t('Shpm.columns.success_count'), key: 'success_count' },
        { name: this.$t('Shpm.columns.success_amount'), key: 'success_amount' },
        { name: this.$t('Shpm.columns.rate'), key: 'rate' }
      ],
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
        async getData(params) {
            if (params) { this.params = params }
            var data = {}
            data.serchData = this.params
            if (!data.serchData.time_create) {
                data.serchData.time_create = [new Date().toLocaleDateString().split('/').join('-') + ' 00:00:00', new Date().toLocaleString().split('/').join('-')]
            }
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            data.order_field = this.order_field
            data.sort = this.sort
            const res = await getMerchantRank(data)
            this.merchantList = res.data
            this.paginationData.total = res.total
        },
        /* 排序*/
        async sort_change({ column }) {
            this.order_field = this.columnList.find(item => item.name === column.label).key
            if (column.order === 'ascending') {
                this.sort = 'asc'
            } else if (column.order === 'descending') {
                this.sort = 'desc'
            } else {
                this.sort = null
            }
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
        }
    }
}
</script>

