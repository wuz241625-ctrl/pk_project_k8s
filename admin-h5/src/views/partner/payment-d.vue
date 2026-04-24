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
      :data="paymentsList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('method.Skzls.form.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.partnerId')">
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.bankName')">
        <template slot-scope="scope">
          {{ bank_type.find(item => item.id == parseInt(scope.row.bank_type)).name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.upi')">
        <template slot-scope="scope">
          {{ scope.row.upi }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.balance')">
        <template slot-scope="scope">
          {{ scope.row.balance }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.certified')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.certified == 1 ? 'success' : 'danger'">
            {{ scope.row.certified == 1 ? $t('method.Skzls.form.certifiedYes') : $t('method.Skzls.form.certifiedNo') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.bankAccount')">
        <template slot-scope="scope">
          {{ scope.row.account }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.ifsc')">
        <template slot-scope="scope">
          {{ scope.row.ifsc }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.accountType')">
        <template slot-scope="scope">
          {{ account_types.find(item => item.id === parseInt(scope.row.account_type)).name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.deleteTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Skzls.form.operation')" width="120">
        <template slot-scope="scope">
          <el-button type="danger" size="small" @click="handleDelete(scope)">
            {{ $t('method.Skzls.form.delete') }}
          </el-button>
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
    getBank_type,
    getPayment,
    deletePayment
} from '@/api/partner'

export default {
    name: 'Skzls',
    data() {
        return {
            paymentsList: [],
            bank_type: [],
            account_types: [
        {
          id: 0,
          name: this.$t('method.Skzls.ds.accountType.saving')
        },
        {
          id: 1,
          name: this.$t('method.Skzls.ds.accountType.current')
        },
        {
          id: 2,
          name: this.$t('method.Skzls.ds.accountType.corporate')
        }
      ],
      formItemList: [
        {
          label: this.$t('method.Skzls.ds.form.id'),
          type: 'input',
          param: 'id'
        },
        {
          label: this.$t('method.Skzls.ds.form.partner_id'),
          type: 'input',
          param: 'partner_id'
        },
        {
          label: this.$t('method.Skzls.ds.form.upi'),
          type: 'input',
          param: 'upi'
        },
        {
          label: this.$t('method.Skzls.ds.form.name'),
          type: 'input',
          param: 'name'
        },
        {
          label: this.$t('method.Skzls.ds.form.account'),
          type: 'input',
          param: 'account'
        },
        {
          label: this.$t('method.Skzls.ds.form.certified'),
          type: 'select',
          selectOptions: [
            {
              value: 0,
              label: this.$t('method.Skzls.ds.certified.not_certified')
            },
            {
              value: 1,
              label: this.$t('method.Skzls.ds.certified.certified')
            }
          ],
          param: 'certified'
        },
        {
          label: this.$t('method.Skzls.ds.form.status'),
          type: 'select',
          selectOptions: [
            {
              value: 0,
              label: this.$t('method.Skzls.ds.statusType.disabled')
            },
            {
              value: 1,
              label: this.$t('method.Skzls.ds.statusType.enabled')
            }
          ],
          param: 'status'
        }
      ],
      exportData: {
        tHeader: [
          this.$t('method.Skzls.ds.form.id'),
          this.$t('method.Skzls.ds.form.partner_id'),
          this.$t('method.Skzls.ds.form.name'),
          this.$t('method.Skzls.ds.form.upi'),
          this.$t('method.Skzls.ds.form.account'),
          this.$t('method.Skzls.ds.form.certified'),
          this.$t('method.Skzls.ds.form.status'),
          this.$t('method.Skzls.ds.form.account_type'),
          this.$t('method.Skzls.ds.form.gmail'),
          this.$t('method.Skzls.ds.form.gmail_pw'),
          this.$t('method.Skzls.ds.form.time_create')
        ],
        filterVal: [
          'id',
          'partner_id',
          'name',
          'upi',
          'account',
          'certified',
          'status',
          'account_type',
          'gmail',
          'gmail_pw',
          'time_create'
        ],
        list: [],
        filename: this.$t('method.Skzls.ds.export.filename')
      },
            params: {},
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            },
        }
    },
    created() {
        this.getBank()
    },
    methods: {
        /* 获取银行*/
        async getBank(params) {
            const res = await getBank_type()
            this.bank_type = res.data
            this.getData()
        },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            var data = {
                serchData: this.params,
                size: this.paginationData.size,
                page: this.paginationData.page,
                is_del: true
            }
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            const res = await getPayment(data)
            console.log(res)
            if (isExport) {
                this.exportData.list = res.data
                // 匹配相关的银行名字和账户类型
                this.exportData.list.forEach((items, index) => {
                    this.exportData.list[index]['bank_name'] = this.bank_type.find(item => items
                        .bank_type == item.id).name
                    this.exportData.list[index]['account_type'] = this.account_types.find(item => items
                        .account_type == item.id).name
                })
                console.log(this.exportData.list)
                this.$refs.search.exportExcel()
            } else {
                this.paymentsList = res.data
                this.count = res.count
                this.paginationData.total = res.total
            }
        },
        /* 删除成员 */
    handleDelete({ $index, row }) {
        this.$confirm(this.$t('method.confirm_delete_payment'), this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            try {
                await deletePayment({
                    'id': row.id,
                    'is_del': true
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.delete_success')
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
