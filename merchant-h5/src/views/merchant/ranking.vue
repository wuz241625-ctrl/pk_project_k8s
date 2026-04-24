<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" @search="search" />
    <el-table
      :data="merchantList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      @sort-change="sort_change"
    >
      <el-table-column align="center" :label="$t('ranking.table.id')" sortable>
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.cellphone')">
        <template slot-scope="scope">
          {{ scope.row.cellphone }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.orderCount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.count }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.orderAmount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.successOrderCount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.success_count }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.successAmount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.success_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.successRate')" sortable>
        <template slot-scope="scope">
          {{ scope.row.rate + '%' }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('ranking.table.payoutAmount')" sortable>
        <template slot-scope="scope">
          {{ scope.row.payout_success_amount }}
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
    getMerchantRank
} from '@/api/merchant'

export default {
    data() {
        return {
            merchantList: [],
            params: {},
            order_field: '',
            sort: null,
            formItemList: [
              {
                "labelKey": "search.channel_id",
                "type": "input",
                "param": "channel_code"
              },
              {
                "labelKey": "ds.search.orderTime",
                "type": "dateTimePicker",
                "param": "time_create",
                "pickerOptions": this.pickerOptionsTimeCreate
              },
              {
                "labelKey": "ds.search.successTime",
                "type": "dateTimePicker",
                "param": "time_success",
                "pickerOptions": this.pickerOptionsTimeSuccess
              },
              {
                "labelKey": "ds.search.merchant_id",
                "type": "input",
                "param": "id"
              }
            ],
            columnList: [{
                name: '订单数',
                key: 'count'
            },
            {
                name: '订单金额',
                key: 'amount'
            },
            {
                name: '成功订单数',
                key: 'success_count'
            },
            {
                name: '成功金额',
                key: 'success_amount'
            },
            {
                name: '成功率',
                key: 'rate'
            }
            ],
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            },
            timeCreateRange: {min: null, max: null}, // 时间范围限制
            timeSuccessRange: {min: null, max: null},
            pickerOptionsTimeCreate: {
                onPick: ({minDate}) => {
                    if (minDate) {
                        this.timeCreateRange.min = minDate
                        this.timeCreateRange.max = new Date(minDate.getTime() + 7 * 24 * 3600 * 1000)
                    } else {
                        this.timeCreateRange.min = null
                        this.timeCreateRange.max = null
                    }
                },
                disabledDate: (time) => {
                    if (this.timeCreateRange.min) {
                        return time < this.timeCreateRange.min || time > this.timeCreateRange.max
                    }
                    return false
                }
            },
            pickerOptionsTimeSuccess: {
                onPick: ({minDate}) => {
                    if (minDate) {
                        this.timeSuccessRange.min = minDate
                        this.timeSuccessRange.max = new Date(minDate.getTime() + 7 * 24 * 3600 * 1000)
                    } else {
                        this.timeSuccessRange.min = null
                        this.timeSuccessRange.max = null
                    }
                },
                disabledDate: (time) => {
                    if (this.timeSuccessRange.min) {
                        return time < this.timeSuccessRange.min || time > this.timeSuccessRange.max
                    }
                    return false
                }
            }
        }
    },
    created() {
        this.getData()
    },
    methods: {
        /* 获取数据*/
        async getData(params) {
            if (this.params.time_create === null) {
                  this.params.time_create = ''
            }
            if (this.params.time_success == null) {
              this.params.time_success = '';
            }
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            var data = {
                'serchData': this.params
            }
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            data.order_field = this.order_field
            data.sort = this.sort
            const res = await getMerchantRank(data)
            this.merchantList = res.data
            this.paginationData.total = res.total
        },
        startTimer() {
            this.timer = setInterval(() => {
                this.getData()
            }, 30000) // 30秒间隔
        },
        clearTimer() {
            if (this.timer) {
                clearInterval(this.timer)
                this.timer = null
            }
        },
        /* 点击查询*/
        async search(params) {
            this.params = params
            // 判断时间范围是否超过7天
            const checkTimeRange = (timeArray) => {
                if (!timeArray || timeArray.length !== 2) return true
                const start = new Date(timeArray[0])
                const end = new Date(timeArray[1])
                const diff = end - start
                return diff <= 31 * 24 * 3600 * 1000 && diff >= 0
            }

            if (params.time_create && !checkTimeRange(params.time_create)) {
                this.$message.error(this.$t('search.timeRangeExceedDays'))
                return
            }

            if (params.time_success && !checkTimeRange(params.time_success)) {
                this.$message.error(this.$t('search.timeRangeExceedDays'))
                return
            }
            // this.clearTimer() // 先清除旧定时器
            await this.getData()
            // this.startTimer()

        },
        /* 排序*/
        async sort_change({
            column
        }) {
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
