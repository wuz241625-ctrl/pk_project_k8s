<template>
  <div class="app-container">
    <baseSearch :form-item-list="formItemList" @search="getData" />
    <el-table :data="operateList" stripe style="width: 100%; margin-top: 30px;" border :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.adminId')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.changeCount')">
        <template slot-scope="scope">
          {{ scope.row.change }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.changeAmount')">
        <template slot-scope="scope">
          {{ scope.row.change_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.transferCount')">
        <template slot-scope="scope">
          {{ scope.row.transfer }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.transferAmount')">
        <template slot-scope="scope">
          {{ scope.row.transfer_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.rechargeCount')">
        <template slot-scope="scope">
          {{ scope.row.recharge }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.rechargeAmount')">
        <template slot-scope="scope">
          {{ scope.row.recharge_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.withdrawCount')">
        <template slot-scope="scope">
          {{ scope.row.withdraw }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.withdrawAmount')">
        <template slot-scope="scope">
          {{ scope.row.withdraw_amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.ds')">
        <template slot-scope="scope">
          {{ scope.row.ds }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('czrz.operateStatistics.table.df')">
        <template slot-scope="scope">
          {{ scope.row.df }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import { getOperate } from '@/api/count'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
  data() {
    return {
      operateList: [], // 数据表
      operateTypeList: [
        { id: 1, name: '登录' }
      ], // 变动类型表
       operateTypeList: [
        { id: 1, name: this.$t('ds.statusType.dispatching') } // 国际化操作类型
      ],
      formItemList: [
        {
          label: this.$t('czrz.ds.form.time_create'), // 国际化日期
          type: 'dateTimePicker',
          pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
          param: 'time_create'
        },
        {
          label: this.$t('czrz.ds.form.admin_id'), // 国际化管理员ID
          type: 'input',
          param: 'admin_id'
        },
        {
          label: this.$t('czrz.ds.form.type'), // 国际化操作类型
          type: 'select',
          selectOptions: [], // 可选项需要在别处定义
          param: 'type'
        },
        {
          label: this.$t('czrz.ds.form.ip'), // 国际化IP地址
          type: 'input',
          param: 'ip'
        }
      ],
      params: {},
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
    // 获取数据
    async getData(params) {
      if (params) { this.params = params }
      var data = { 'serchData': this.params }
      data.size = this.paginationData.size
      data.page = this.paginationData.page
      const res = await getOperate(data)
      this.operateList = res.data
      console.log(this.operateList)
      this.paginationData.total = res.total
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
  .el-button{
    margin: 3px;
  }
</style>
