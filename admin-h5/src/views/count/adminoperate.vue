<template>
  <div class="app-container">
    <baseSearch :form-item-list="formItemList" @search="getData" />
    <el-table :data="operateList" stripe style="width: 100%;margin-top:30px;" border :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('glyczxt.table.adminId')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.changeCount')">
        <template slot-scope="scope">
          {{ scope.row.change }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.changeAmount')">
        <template slot-scope="scope">
          {{ scope.row.change_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.transferCount')">
        <template slot-scope="scope">
          {{ scope.row.transfer }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.transferAmount')">
        <template slot-scope="scope">
          {{ scope.row.transfer_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.rechargeCount')">
        <template slot-scope="scope">
          {{ scope.row.recharge }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.rechargeAmount')">
        <template slot-scope="scope">
          {{ scope.row.recharge_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.withdrawCount')">
        <template slot-scope="scope">
          {{ scope.row.withdraw }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.withdrawAmount')">
        <template slot-scope="scope">
          {{ scope.row.withdraw_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.ds')">
        <template slot-scope="scope">
          {{ scope.row.ds }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('glyczxt.table.df')">
        <template slot-scope="scope">
          {{ scope.row.df }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import { adminOperate } from '@/api/count'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    data() {
        return {
            operateList: [], // 数据表
            formItemList: [
            {
            label: this.$t('glyczxt.ds.form.time'), // 使用 $t 方法获取翻译
            type: 'dateTimePicker',
            pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
            param: 'time_create'
            }
            ],
            params: {}
        }
    },
    created() {
        this.getData()
    },
    methods: {
    /* 获取数据 */
        async getData(params) {
            this.params = { 'time_create': [new Date().toLocaleDateString().split('/').join('-') + ' 00:00:00', new Date().toLocaleString().split('/').join('-')] }
            if (params) {
                this.params = params
            }
            var data = { 'serchData': this.params }
            const res = await adminOperate(data)
            this.operateList = res.data
        }
    }
}
</script>
<style lang="scss" scoped>
  .el-button{
    margin: 3px;
  }
</style>
