<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" @search="getData" />

    <!-- Add Button -->
    <el-button type="primary" @click="handleAdd">{{ $t('merchant.addButton') }}</el-button>

    <!-- Data Table -->
    <el-table
      :data="merchantList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('merchant.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.cellphone')">
        <template slot-scope="scope">
          {{ scope.row.cellphone }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.balance')">
        <template slot-scope="scope">
          {{ scope.row.balance }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.balanceFrozen')">
        <template slot-scope="scope">
          {{ scope.row.balance_frozen }}
        </template>
      </el-table-column>
      <!-- 国际化调整0804 -->
      <el-table-column align="center" :label="$t('merchant.table.dfStatus')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.status_df === 1 ? 'primary' : 'info'">
            {{ $t(`merchant.status.${scope.row.status_df}`) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.status')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.status === 1 ? 'primary' : 'info'">
            {{ $t(`merchant.status1.${scope.row.status}`) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.registerTime')">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchant.table.operation')" width="220px">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleChannel(scope)">{{ $t('merchant.table.channel') }}</el-button>
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('merchant.table.edit') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Channel Dialog -->
    <el-dialog :visible.sync="channel_dialogVisible" :title="$t('merchant.channelDialog.title')">
      <el-form label-width="140px" label-position="left" style="max-width: 360px">
        <el-form-item v-for="(item, index) in merchant_channel" :key="index" :label="item.code + ' ' + item.name">
          <el-input v-model="item.rate" :placeholder="$t('merchant.channelDialog.ratePlaceholder')" />
        </el-form-item>
      </el-form>
      <div style="text-align: right;">
        <el-button type="primary" @click="channel_dialogVisible = false">{{ $t('merchant.channelDialog.cancel') }}</el-button>
        <el-button type="danger" @click="confirmChannel">{{ $t('merchant.channelDialog.confirm') }}</el-button>
      </div>
    </el-dialog>

    <!-- Merchant Dialog -->
    <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('merchant.dialog.edit') : $t('merchant.dialog.add')">
      <el-form :model="merchant" label-width="180px" label-position="left">
        <el-form-item :label="$t('merchant.dialog.cellphone')">
          <el-input v-model="merchant.cellphone" :disabled="dialogType === 'edit'" :placeholder="$t('merchant.dialog.cellphonePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('merchant.dialog.name')">
          <el-input v-model="merchant.name" :disabled="dialogType === 'edit'" :placeholder="$t('merchant.dialog.namePlaceholder')" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'edit'" :label="$t('merchant.dialog.dfRate')">
          <el-input v-model="merchant.rate_df" :placeholder="$t('merchant.dialog.dfRatePlaceholder')" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'edit'" :label="$t('merchant.dialog.feeDf')">
          <el-input v-model="merchant.fee_df" :placeholder="$t('merchant.dialog.feeDfPlaceholder')" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'new'" :label="$t('merchant.dialog.google')">
          <el-input v-model="merchant.google" :placeholder="$t('merchant.dialog.googlePlaceholder')" />
        </el-form-item>
      </el-form>
      <div style="text-align: right;">
        <el-button type="primary" @click="dialogVisible = false">{{ $t('merchant.channelDialog.cancel') }}</el-button>
        <el-button type="danger" @click="confirmMerchat">{{ $t('merchant.channelDialog.confirm') }}</el-button>
      </div>
    </el-dialog>

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
    deepClone
} from '@/utils'
import {
    getMerchant,
    addMerchant,
    updateMerchant,
    getMerchantChannel,
    updateMerchantChannel,
} from '@/api/merchant'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
  data() {
    return {
      params: {},
      statusTypePayment: [
        { 'id': 0, 'name': '未开启', 'type': 'warning' },
        { 'id': 1, 'name': '已开启', 'type': 'danger' },
      ],
      statusTypeStatus: [
        { 'id': 0, 'name': '禁用', 'type': 'warning' },
        { 'id': 1, 'name': '启用', 'type': 'danger' },
      ],
      merchant: {},
      merchantList: [],
      merchant_channel: {},
      dialogVisible: false,
      channel_dialogVisible: false,
      dialogType: 'new',
      formItemList: [
        {
          labelKey: 'search.id',
          type: 'input',
          param: 'id'
        },
        {
          labelKey: 'search.cellphone',
          type: 'input',
          param: 'cellphone'
        },
        {
          labelKey: 'search.name',
          type: 'input',
          param: 'name'
        },
        {
          labelKey: 'search.payment', // 更新为国际化的键
          type: 'select',
          selectOptions: [],
          param: 'payment'
        },
        {
          labelKey: 'search.status',
          type: 'select',
          selectOptions: [],
          param: 'status'
        },
        {
          labelKey: 'search.registration_date',
          type: 'dateTimePicker',
          pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
          param: 'time_create'
        }
      ],
      paginationData: {
        page: 1,
        size: 10,
        total: 0
      }
    }
  },
  created() {
    
    this.statusTypePayment.forEach(statusTypePayment => {
      this.formItemList.find(item => item.param === 'payment').selectOptions.push({
        value: statusTypePayment.id,
        label: this.$t(`merchant.status1.${statusTypePayment.id}`) // 使用国际化
      })
    })    
    
    this.statusTypeStatus.forEach(statusTypeStatus => {
      this.formItemList.find(item => item.param === 'status').selectOptions.push({
        value: statusTypeStatus.id,
        label: this.$t(`merchant.status.${statusTypeStatus.id}`) // 使用国际化
      })
    })  

    this.getData()
  },
  methods: {
        /* 获取数据*/
        async getData(params) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            var data = {
                'serchData': this.params
            }
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            const res = await getMerchant(data)
            this.merchantList = res.data
            this.paginationData.total = res.total
        },
        /* 设置通道*/
        async handleChannel(scope) {
            this.merchant_channel = {}
            this.channel_dialogVisible = true
            this.merchant = deepClone(scope.row)
            const res = await getMerchantChannel({
                'id': scope.row.id
            })
            this.merchant_channel = res.data
        },
        /* 确认编辑通道*/
        async confirmChannel() {
            this.channel_dialogVisible = false
            var data = {}
            data.id = this.merchant.id
            data.merchant_channel = this.merchant_channel
            try { await updateMerchantChannel(data) } catch (err) { return }
            this.dialogVisible = false
            this.$message({
                type: 'success',
                message: this.$t('method.saveSuccess')
            })
        },
        /* 新增商户*/
        handleAdd() {
            this.dialogType = 'new'
            this.dialogVisible = true
            this.merchant = {}
        },
        /* 编辑商户*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.merchant = deepClone(scope.row)
        },
        /* 确认新增编辑*/
        async confirmMerchat() {
            var data = {}
            if (this.dialogType === 'edit') {
                data.id = this.merchant.id
                data.rate_df = this.merchant.rate_df
                data.fee_df = this.merchant.fee_df
                try { await updateMerchant(data) } catch (err) { return }
            } else {
                data.cellphone = this.merchant.cellphone
                data.name = this.merchant.name
                data.google = this.merchant.google
                try { await addMerchant(data) } catch (err) { return }
            }
            const { cellphone, name } = this.merchant
            this.dialogVisible = false
            this.$notify({
                title: this.$t('method.saveSuccess'),
                dangerouslyUseHTMLString: true,
                message: `
                    <div>this.$t('method.phone ${cellphone}</div>
                    <div>this.$t('method.name'): ${name}</div>
                  `,
                type: 'success'
            })
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
