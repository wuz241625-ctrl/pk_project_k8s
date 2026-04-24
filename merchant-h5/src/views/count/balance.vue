<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      :form-item-list="formItemList"
      :export-data="exportData"
      @search="getData"
      @export="getData"
    />
    <el-table
      :data="recordList"
      stripe
      style="width: 100%;margin-top:30px;"
      border
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('balance.table.serialNumber')" width="260">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('balance.table.merchantOrderNumber')" width="260">
        <template slot-scope="scope">
          {{ scope.row.merchant_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('balance.table.beforeChange')">
        <template slot-scope="scope">
          {{ scope.row.change_before }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('balance.table.changeAmount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('balance.table.afterChange')">
        <template slot-scope="scope">
          {{ scope.row.change_after }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('balance.table.time')" width="200">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('balance.table.type')">
        <template slot-scope="scope">
          {{ $t(`balance.types.${scope.row.record_type}`) }}
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
    getBalanceRecord
} from '@/api/count'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
  data() {
    return {
      params: {},
      recordList: [], // 数据表
      recordType: [
        { id: 0, name: this.$t('balance.types.0') },
        { id: 1, name: this.$t('balance.types.1') },
        { id: 2, name: this.$t('balance.types.2') },
        { id: 3, name: this.$t('balance.types.3') },
        { id: 4, name: this.$t('balance.types.4') },
        { id: 6, name: this.$t('balance.types.6') },
        { id: 9, name: this.$t('balance.types.9') },
        { id: 10, name: this.$t('balance.types.10') }
      ],
      formItemList: [
              {
                  labelKey: 'search.code',
                  type: 'input',
                  param: 'code'
              },
              {
                  labelKey: 'search.merchant_code',
                  type: 'input',
                  param: 'merchant_code'
              },
              {
                  labelKey: 'search.amount',
                  type: 'input',
                  param: 'amount'
              },
              {
                  labelKey: 'search.time_create',
                  type: 'dateTimePicker',
                  pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                  param: 'time_create'
              },
              {
                  labelKey: 'search.record_type',
                  type: 'select',
                  selectOptions: [],
                  param: 'record_type'
              }
      ],
      exportData: {
        tHeader: this.$t('balance.export.header'),
        filterVal: ['code', 'merchant_code', 'change_before', 'amount', 'change_after', 'time_create', 'record_type'],
        list: [],
        filename: this.$t('balance.export.filename')
      },
      paginationData: {
        page: 1,
        size: 10,
        total: 0
      }
    }
  },
  created() {
    this.recordType.forEach(recordtype => {
      this.formItemList.find(item => item.type === 'select').selectOptions.push({
        value: recordtype.id,
        label: recordtype.name
      })
    })
    this.getData()
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
            const res = await getBalanceRecord(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.recordList = res.data
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
