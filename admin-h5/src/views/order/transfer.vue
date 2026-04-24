<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      :form-item-list="formItemList"
      :export-data="exportData"
      @search="getData"
      @export="getData"
    />
    <el-button type="primary" @click="handleAddTransfer">{{ $t('method.Transfer.addTransfer') }}</el-button>
    <el-form>
      <el-button type="warning" plain @click="handlecopy(count.processing)">
        {{ $t('method.Transfer.processing') }}：{{ count.processing }}
      </el-button>
      <el-button type="warning" plain @click="handlecopy(count.processingAmount)">
        {{ $t('method.Transfer.processingAmount') }}：{{ count.processing_amount }}
      </el-button>
      <el-button type="primary" plain @click="handlecopy(count.amount)">
        {{ $t('method.Transfer.totalAmount') }}：{{ count.amount }}
      </el-button>
    </el-form>

    <el-table
      :data="orderList"
      stripe
      style="width: 100%; margin-top: 30px;"
      border
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"
    >
      <el-table-column fixed="left" align="center" :label="$t('method.Transfer.orderNumber')" width="240">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Transfer.merchantID')">
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Transfer.receiverMerchantID')">
        <template slot-scope="scope">
          {{ scope.row.to_partner_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Transfer.adminID')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Transfer.orderAmount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.Transfer.status')">
        <template slot-scope="scope">
          <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
            {{ statusType.find(item => item.id === scope.row.status).name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Transfer.remark')" width="160">
        <template slot-scope="scope">
          {{ scope.row.remark }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Transfer.orderTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Transfer.successTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_success }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Transfer.updateTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_updated }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" align="center" :label="$t('method.Transfer.action')" width="220px">
        <template slot-scope="scope">
          <el-button
            v-if="scope.row.status === 1"
            type="warning"
            size="small"
            @click="confirmFinish(scope)"
          >{{ $t('method.Transfer.confirmComplete') }}</el-button>
          <el-button
            v-if="scope.row.status === 1"
            type="danger"
            size="small"
            @click="handleCancel(scope)"
          >{{ $t('method.Transfer.reject') }}</el-button>
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

    <el-dialog :visible.sync="dialogVisible" :title="$t('method.Transfer.addTransfer')" :close-on-click-modal="false">
      <el-form :model="transfer" label-width="auto" label-position="left">
        <el-form-item :label="$t('method.Transfer.merchantID')">
          <el-input v-model="transfer.partner_id" :placeholder="$t('method.Transfer.enterMerchantID')" />
        </el-form-item>
        <el-form-item :label="$t('method.Transfer.amount')">
          <el-input v-model="transfer.amount" :placeholder="$t('method.Transfer.enterAmount')" />
        </el-form-item>
        <el-form-item :label="$t('method.Transfer.receiverMerchantID')">
          <el-input v-model="transfer.to_partner_id" :placeholder="$t('method.Transfer.enterReceiverMerchantID')" />
        </el-form-item>
        <el-form-item :label="$t('method.Transfer.remark')">
          <el-input v-model="transfer.remark" :placeholder="$t('method.Transfer.enterRemark')" />
        </el-form-item>
      </el-form>
      <div style="text-align: right;">
        <el-button type="primary" @click="dialogVisible = false">{{ $t('method.Transfer.cancel') }}</el-button>
        <el-button type="danger" @click="confirmTransfer">{{ $t('method.Transfer.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>


<script>
import {
    deepClone
} from '@/utils'
import {
    getTransfer,
    handleTransfer,
    createTransfer,
    getPayment
} from '@/api/recharge'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

const defaulttransfer = {
    partner_id: '',
    amount: '',
    to_partner_id: '',
    remark: ''
}

export default {
    name: 'Mszzdd',
    data() {
        return {
            transfer: Object.assign({}, defaulttransfer),
            orderList: [], // 数据表
            dialogVisible: false,
            statusType: [{
                'id': 0,
                'name': this.$t('method.Transfer.statusType.0'),
                'type': 'warning'
            },
            {
                'id': 1,
                'name': this.$t('method.Transfer.statusType.1'),
                'type': 'warning'
            },
            {
                'id': 2,
                'name': this.$t('method.Transfer.statusType.2'),
                'type': 'success'
            },
            {
                'id': -1,
                'name': this.$t('method.Transfer.statusType.-1'),
                'type': 'info'
            }
            ],
             formItemList: [
        { label: this.$t('method.Transfer.form.code'), type: 'input', param: 'code' },
        {
          label: this.$t('method.Transfer.form.status'),
          type: 'select',
          selectOptions: [
            { value: 0, label: this.$t('method.Transfer.statusType.0') },
            { value: 1, label: this.$t('method.Transfer.statusType.1') },
            { value: 2, label: this.$t('method.Transfer.statusType.2') },
            { value: -1, label: this.$t('method.Transfer.statusType.-1') }
          ],
          param: 'status'
        },
        { label: this.$t('method.Transfer.form.partner_id'), type: 'input', param: 'partner_id' },
        { label: this.$t('method.Transfer.form.to_partner_id'), type: 'input', param: 'to_partner_id' },
        { label: this.$t('method.Transfer.form.admin_id'), type: 'input', param: 'admin_id' },
        { label: this.$t('method.Transfer.form.amount'), type: 'input', param: 'amount' },
        { label: this.$t('method.Transfer.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' },
        { label: this.$t('method.Transfer.form.time_success'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_success' }
      ],
      params: {},
      exportData: {
        tHeader: [
          this.$t('method.Transfer.export.code'),
          this.$t('method.Transfer.export.partner_id'),
          this.$t('method.Transfer.export.to_partner_id'),
          this.$t('method.Transfer.export.admin_id'),
          this.$t('method.Transfer.export.amount'),
          this.$t('method.Transfer.export.status'),
          this.$t('method.Transfer.export.time_create'),
          this.$t('method.Transfer.export.time_success'),
          this.$t('method.Transfer.export.time_updated'),
          this.$t('method.Transfer.export.remark')
        ],
        filterVal: [
          'code', 'partner_id', 'to_partner_id', 'admin_id', 'amount', 'status', 'time_create',
          'time_success', 'time_updated', 'remark'
        ],
        list: [],
        filename: this.$t('method.Transfer.export.filename')
      },
            count: {
                failOrder: 0,
                successOrder: 0,
                rate: 0,
                processing: 0,
                amount: 0
            },
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
                this.paginationData.page = 1
                this.paginationData.size = 10
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
            const res = await getTransfer(data)
            if (isExport) {
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.orderList = res.data
                this.count = res.count
                this.paginationData.total = res.total
            }
        },
        /* 点击搜索 */
        handlesearch(params) {
            this.serchData = params
            this.getData()
        },
         /* 点击复制 */
    handleCopy(amount) {
        const oInput = document.createElement('input')
        oInput.value = amount
        document.body.appendChild(oInput)
        oInput.select() // 选择对象;
        document.execCommand('Copy') // 执行浏览器复制命令
        this.$notify({
            title: this.$t('method.copy_success'),
            type: 'success'
        })
    },
    /* 添加转账 */
    async confirmTransfer() {
        var data = this.transfer
        try {
            await createTransfer(data)
        } catch (err) {
            return
        }
        const {
            partner_id,
            amount,
            to_partner_id,
            remark
        } = this.transfer
        this.dialogVisible = false
        this.$notify({
            title: this.$t('method.add_success'),
            dangerouslyUseHTMLString: true,
            message: this.$t('method.transfer_details', { partner_id, amount, to_partner_id, remark }),
            type: 'success'
        })
        this.getData()
    },
    /* 确认转账 */
    confirmFinish({ $index, row }) {
        this.$confirm(this.$t('method.confirm_transfer'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'code': row.code,
                'status': 2
            }
            try {
                await handleTransfer(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.confirm_success')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 驳回 */
    async handleCancel({ $index, row }) {
        this.$confirm(this.$t('method.reject_confirm'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            const data = {
                'code': row.code,
                'status': -1
            }
            try {
                await handleTransfer(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.reject_success')
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
    },
        /* 新增转账*/
    handleAddTransfer() {
        this.transfer = Object.assign({}, defaulttransfer)
        this.dialogVisible = true
    }
  }
}
</script>
<style lang="scss" scoped>
    .el-button {
        margin: 3px;
    }
</style>
