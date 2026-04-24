<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" :export-data="exportData" @search="getData" @export="getData" />
    <el-form>
      <el-button type="primary" plain @click="handlecopy(daily[6])">{{ $t('cwbb.button.copyTotalChangeAmount') }}：{{ daily[6] }}</el-button>
      <el-button type="primary" plain @click="handlecopy(daily[0])">{{ $t('cwbb.button.copyMerchantBalance') }}：{{ daily[0] }}</el-button>
      <el-button type="primary" plain @click="handlecopy(daily[2])">{{ $t('cwbb.button.copyPartnerBalance') }}：{{ daily[2] }}</el-button>
    </el-form>
    <el-table :data="dailyList" stripe style="width: 100%;margin-top:30px;" border :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('cwbb.table.date')">
        <template slot-scope="scope">
          {{ scope.row.date }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('cwbb.table.amountType')">
        <template slot-scope="scope">
          {{getTypeName(scope.row.balance_type,"1")}}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('cwbb.table.changeType')">
        <template slot-scope="scope">
          {{getTypeName(scope.row.record_type,"2")}}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('cwbb.table.changeAmount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
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
import { getDaily } from '@/api/count'

export default {
    data() {
        return {
            dailyList: [], // 数据表
            daily: {}, // 数据统计
            amountTypeList: [
        { id: 0, name: this.$t('cwbb.ds.amountType.collection') },
        { id: 1, name: this.$t('cwbb.ds.amountType.payment') },
        { id: 2, name: this.$t('cwbb.ds.amountType.withdrawal') },
        { id: 3, name: this.$t('cwbb.ds.amountType.commission') },
        { id: 4, name: this.$t('cwbb.ds.amountType.freeze') },
        { id: 5, name: this.$t('cwbb.ds.amountType.deposit') },
        { id: 6, name: this.$t('cwbb.ds.amountType.manual') },
        { id: 7, name: this.$t('cwbb.ds.amountType.topUp') },
        { id: 8, name: this.$t('cwbb.ds.amountType.transfer') },
        { id: 9, name: this.$t('cwbb.ds.amountType.rejected_payment') }
      ],
      changeTypeList: [
        { id: 0, name: this.$t('cwbb.ds.changeType.merchant_balance') },
        { id: 1, name: this.$t('cwbb.ds.changeType.store_balance') }
      ],
      formItemList: [
        {
          label: this.$t('cwbb.ds.form.date'),
          type: 'datePicker',
          param: 'date'
        },
        {
          label: this.$t('cwbb.ds.form.balance_type'),
          type: 'select',
          selectOptions: [], // You should populate this with translated options
          param: 'balance_type'
        },
        {
          label: this.$t('cwbb.ds.form.change_type'),
          type: 'select',
          selectOptions: [], // You should populate this with translated options
          param: 'record_type'
        },
        {
          label: this.$t('cwbb.ds.form.amount'),
          type: 'input',
          param: 'amount'
        }
      ],
      params: {},
      exportData: {
        tHeader: [
          this.$t('cwbb.ds.export.date'),
          this.$t('cwbb.ds.export.amount_type'),
          this.$t('cwbb.ds.export.change_type'),
          this.$t('cwbb.ds.export.change_amount')
        ],
        filterVal: ['date', 'balance_type', 'record_type', 'amount'],
        list: [],
        filename: this.$t('cwbb.ds.export.financial_daily_report')
      },
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            }
        }
    },
    created() {
        this.amountTypeList.forEach(amountType => {
            this.formItemList.find(item => item.param === 'record_type').selectOptions.push({ value: amountType.id, label: amountType.name })
        })
        this.changeTypeList.forEach(amountType => {
            this.formItemList.find(item => item.param === 'balance_type').selectOptions.push({ value: amountType.id, label: amountType.name })
        })
        this.getData()
    },
    methods: {
    /* 获取数据 */
        async getData(params, isExport = false) {
            if (params) { this.params = params }
            var data = { 'serchData': this.params }
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            const res = await getDaily(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.dailyList = res.data
                this.daily = res.count
                this.paginationData.total = res.total
            }
        },
        /* 复制 */
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
        getTypeName(data,type) {
          let changeType = Node
          if(type === "1"){
              changeType = this.changeTypeList.find(item => item.id === data)
          }else {
              changeType = this.amountTypeList.find(item => item.id === data)
          }
          if(changeType){
              return changeType.name
          }else {
              return ""
          }
        }
    }
}
</script>
<style lang="scss" scoped>
  .el-button{
    margin: 3px;
  }
</style>
