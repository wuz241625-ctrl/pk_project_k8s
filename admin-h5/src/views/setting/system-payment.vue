<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      :form-item-list="formItemList"
      :export-data="exportData"
      @search="getData"
      @export="getData"
    />
    <el-button type="primary" @click="handleAddPayment">{{ $t('method.xtskxx.button.addPayment') }}</el-button>
    <el-table
      :data="paymentsList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('method.xtskxx.table.account')">
        <template slot-scope="scope">
          {{ scope.row.account }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.xtskxx.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.xtskxx.table.bank')">
        <template slot-scope="scope">
          {{ scope.row.bank }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.xtskxx.table.ifsc')">
        <template slot-scope="scope">
          {{ scope.row.ifsc }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.xtskxx.table.adminId')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.xtskxx.table.timeCreate')">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.xtskxx.table.action')">
        <template slot-scope="scope">
          <el-button
            :type="scope.row.status===0?'warning':'success'"
            size="small"
            @click="handleChangeStatus(scope)"
          >
            {{ scope.row.status===1 ? $t('method.xtskxx.table.disable') : $t('method.xtskxx.table.enable') }}
          </el-button>
          <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('method.xtskxx.table.delete') }}</el-button>
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

    <el-dialog :visible.sync="dialogVisible" :title="$t('method.xtskxx.dialog.addTitle')">
      <el-form :model="payment" label-width="80px" label-position="left">
        <el-form-item :label="$t('method.xtskxx.dialog.account')">
          <el-input v-model="payment.account" :placeholder="$t('method.xtskxx.dialog.accountPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.xtskxx.dialog.name')">
          <el-input v-model="payment.name" :placeholder="$t('method.xtskxx.dialog.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.xtskxx.dialog.bank')">
          <el-input v-model="payment.bank" :placeholder="$t('method.xtskxx.dialog.bankPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.xtskxx.dialog.ifsc')">
          <el-input v-model="payment.ifsc" :placeholder="$t('method.xtskxx.dialog.ifscPlaceholder')" />
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('method.xtskxx.dialog.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('method.xtskxx.dialog.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
    getPayment,
    addPayment,
    updatePayment,
    deletePayment
} from '@/api/setting'

const defaultpayment = {
    account: '',
    name: '',
    bank: '',
    ifsc: ''
}

export default {
    data() {
        return {
            payment: Object.assign({}, defaultpayment),
            paymentsList: [],
            dialogVisible: false,
            dialogType: 'new',
            formItemList: [
        {
          label: this.$t('method.xtskxx.ds.form.account'),
          type: 'input',
          param: 'account'
        },
        {
          label: this.$t('method.xtskxx.ds.form.name'),
          type: 'input',
          param: 'name'
        },
        {
          label: this.$t('method.xtskxx.ds.form.bank'),
          type: 'input',
          param: 'bank'
        },
        {
          label: this.$t('method.xtskxx.ds.form.ifsc'),
          type: 'input',
          param: 'ifsc'
        },
        {
          label: this.$t('method.xtskxx.ds.form.admin_id'),
          type: 'input',
          param: 'admin_id'
        },
        {
          label: this.$t('method.xtskxx.ds.form.status'),
          type: 'select',
          selectOptions: [
            {
              value: 0,
              label: this.$t('method.xtskxx.ds.statusType.disabled')
            },
            {
              value: 1,
              label: this.$t('method.xtskxx.ds.statusType.enabled')
            }
          ],
          param: 'status'
        }
      ],
      exportData: {
        isShow: true,
        tHeader: [
          this.$t('method.xtskxx.ds.export.account'),
          this.$t('method.xtskxx.ds.export.name'),
          this.$t('method.xtskxx.ds.export.bank'),
          this.$t('method.xtskxx.ds.export.ifsc'),
          this.$t('method.xtskxx.ds.export.admin_id')
        ],
        filterVal: ['account', 'name', 'bank', 'ifsc', 'admin_id'],
        list: [],
        filename: this.$t('method.xtskxx.ds.export.system_collection_info')
      },
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
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
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
            const res = await getPayment(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.paymentsList = res.data
                this.paginationData.total = res.total
            }
        },
        /* 新增成员*/
        handleAddPayment() {
            this.payment = Object.assign({}, defaultpayment)
            this.dialogType = 'new'
            this.dialogVisible = true
        },
        /* 删除成员 */
    handleDelete({ $index, row }) {
        this.$confirm(this.$t('method.handleDelete.confirmMessage'), this.$t('method.handleDelete.title'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async () => {
            try {
                await deletePayment({ 'id': row.id });
            } catch (err) {
                return;
            }
            this.getData();
            this.$message({
                type: 'success',
                message: this.$t('method.handleDelete.successMessage')
            });
        }).catch(() => {});
    },
    /* 改变状态 */
    handleChangeStatus({ $index, row }) {
        const tipsString = row.status === 1 ? this.$t('method.handleChangeStatus.disable') : this.$t('method.handleChangeStatus.enable');
        this.$confirm(`${this.$t('method.handleChangeStatus.confirmMessageStart')}${tipsString}${this.$t('method.handleChangeStatus.confirmMessageEnd')}`, this.$t('method.handleChangeStatus.title'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async () => {
            const data = {
                id: row.id,
                status: Math.abs(row.status - 1)
            };
            try {
                await updatePayment(data);
            } catch (err) {
                return;
            }
            this.$message({
                type: 'success',
                message: `${tipsString}${this.$t('method.handleChangeStatus.successMessage')}`
            });
            this.getData();
        }).catch(() => {});
    },
    /* 改变分页大小 */
    handleSizeChange(val) {
        this.paginationData.size = val;
        this.getData();
    },
    /* 改变当前页 */
    handleCurrentChange(val) {
        this.paginationData.page = val;
        this.getData();
    },
    /* 确认新增 */
    async confirmRole() {
        const data = this.payment;
        try {
            await addPayment(data);
        } catch (err) {
            return;
        }
        const { account, name, bank, ifsc } = this.payment;
        this.dialogVisible = false;
        this.$notify({
            title: this.$t('method.confirmRole.title'),
            dangerouslyUseHTMLString: true,
            message: `
                <div>${this.$t('method.confirmRole.account')}: ${account}</div>
                <div>${this.$t('method.confirmRole.name')}: ${name}</div>
                <div>${this.$t('method.confirmRole.bank')}: ${bank}</div>
                <div>${this.$t('method.confirmRole.ifsc')}: ${ifsc}</div>
            `,
            type: 'success'
        });
        this.getData();
    }
}
}
</script>
