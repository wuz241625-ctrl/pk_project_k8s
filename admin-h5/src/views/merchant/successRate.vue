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
      <el-table-column align="center" :label="this.$t('method.successRate.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="this.$t('method.successRate.phone')">
        <template slot-scope="scope">
          {{ scope.row.cellphone }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="this.$t('method.successRate.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="this.$t('method.successRate.balance')" sortable>
        <template slot-scope="scope">
          {{ scope.row.balance }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="this.$t('method.successRate.successOrders')">
        <el-table-column align="center" :label="this.$t('method.successRate.successOrders15m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.success_count_15m }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="this.$t('method.successRate.successOrders30m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.success_count_30m }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="this.$t('method.successRate.successOrders60m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.success_count_60m }}
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column align="center" :label="this.$t('method.successRate.successAmount')">
        <el-table-column align="center" :label="this.$t('method.successRate.successAmount15m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.success_amount_15m }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="this.$t('method.successRate.successAmount30m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.success_amount_30m }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="this.$t('method.successRate.successAmount60m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.success_amount_60m }}
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column align="center" :label="this.$t('method.successRate.successRate')">
        <el-table-column align="center" :label="this.$t('method.successRate.successRate15m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.rate_15m + '%' }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="this.$t('method.successRate.successRate30m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.rate_30m + '%' }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="this.$t('method.successRate.successRate60m')" sortable>
          <template slot-scope="scope">
            {{ scope.row.rate_60m + '%' }}
          </template>
        </el-table-column>
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
import { getMerchantSuccessRate } from '@/api/merchant'

export default {
    name: 'Shcgl',
    data() {
        return {
            merchantList: [],
            order_field: '',
            sort: null,
            formItemList: [

                {
                    label: 'ID',
                    type: 'input',
                    param: 'id'
                }
            ],
            params: {},
            columnList: [
                { name: this.$t('method.successRate.balance'), key: 'balance' },
                { name: this.$t('method.successRate.successOrders15m'), key: 'success_count_15m' },
                { name: this.$t('method.successRate.successAmount15m'), key: 'success_amount_15m' },
                { name: this.$t('method.successRate.successRate15m'), key: 'rate_15m' },
                { name: this.$t('method.successRate.successOrders30m'), key: 'success_count_30m' },
                { name: this.$t('method.successRate.successAmount30m'), key: 'success_amount_30m' },
                { name: this.$t('method.successRate.successRate30m'), key: 'rate_30m' },
                { name: this.$t('method.successRate.successOrders60m'), key: 'success_count_60m' },
                { name: this.$t('method.successRate.successAmount60m'), key: 'success_amount_60m' },
                { name: this.$t('method.successRate.successRate30m'), key: 'rate_60m' }
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

            data.size = this.paginationData.size
            data.page = this.paginationData.page
            data.order_field = this.order_field
            data.sort = this.sort
            const res = await getMerchantSuccessRate(data)
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

