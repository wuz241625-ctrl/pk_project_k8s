<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" @search="getData" />
    <el-button type="primary" @click="handleAdd">{{ $t("method.Shlb.button.add_merchant") }}</el-button>
    <el-table
      :data="merchantList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background: '#DCDFE6', color: '#606266'}"  @sort-change="sort_change"
    >
      <el-table-column align="center" :label="$t('method.Shlb.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.phone')">
        <template slot-scope="scope">
          {{ scope.row.cellphone }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.pid')">
        <template slot-scope="scope">
          {{ scope.row.pid }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.balance')"  sortable>
        <template slot-scope="scope">
          {{ scope.row.balance }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.frozen_balance')">
        <template slot-scope="scope">
          {{ scope.row.balance_frozen }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.df_status')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.status_df===1 ? 'primary' : 'info'">
            {{ scope.row.status_df===1 ? $t('method.Shlb.status.open') : $t('method.Shlb.status.closed') }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- <el-table-column align="center" :label="$t('method.Shlb.table.decimalPointCallback')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.decimal_amt_flag === 1 ? 'success' : 'info'">
            {{ scope.row.decimal_amt_flag === 1 ? $t('method.Shlb.status.enabled') : $t('method.Shlb.status.disabled') }}
          </el-tag>
        </template>
      </el-table-column> -->
      <el-table-column align="center" label="Notify回调类型">
        <template slot-scope="scope">
          <el-tag :type="scope.row.notify_callback_type === 1 ? 'warning' : 'primary'">
            {{ scope.row.notify_callback_type === 1 ? '小数点回调' : '整数回调' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.registration_time')">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Shlb.table.actions')" width="220px">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleChannel(scope)">{{ $t('method.Shlb.button.channel') }}</el-button>
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('method.Shlb.button.edit') }}</el-button>
          <el-button :type="scope.row.status===0 ? 'warning' : 'success'" size="small" @click="changeStatus(scope)">
            {{ scope.row.status===1 ? $t('method.Shlb.button.disable') : $t('method.Shlb.button.enable') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="channel_dialogVisible" :title="$t('method.Shlb.dialog.channel_settings')" :close-on-click-modal="false">
      <el-form label-width="140px" label-position="left">
        <el-form-item v-for="(item, index) in merchant_channel" :key="index" :label="item.code + ' ' + item.name">
          <el-switch v-model="item.status" :active-value="1" :inactive-value="0" active-color="#13ce66" />
          <label style="margin-left: 30px;">{{ $t('method.Shlb.label.rate') }}：</label>
          <el-input v-model="item.rate" :placeholder="$t('method.Shlb.placeholder.set_rate')" style="width: 80px;" />
          <label style="margin-left: 30px;">{{ $t('method.Shlb.label.third_party_payment') }}：</label>
          <el-select v-model="item.otherpay" style="width: 220px;" clearable popper-class="otherpay-dropdown" :placeholder="$t('method.Shlb.placeholder.select_third_party_payment')">
            <el-option v-for="i in otherPayList" :key="i.id" :label="getOtherPayOptionLabel(i)" :value="i.id" />
          </el-select>
          <label style="margin-left: 30px;">{{ $t('method.Shlb.label.force_third_party') }}：</label>
          <el-switch v-model="item.is_force" :active-value="1" :inactive-value="0" active-color="#13ce66" />
          <label style="margin-left: 30px;">{{ $t('method.Shlb.label.channel_redirect') }}：</label>
          <el-input v-model="item.target_channel" placeholder="" style="width: 80px;" />
        </el-form-item>
        <div style="text-align:right;">
          <el-button type="primary" @click="channel_dialogVisible=false">{{ $t('method.Shlb.button.cancel') }}</el-button>
          <el-button type="danger" @click="confirmChannel">{{ $t('method.Shlb.button.confirm') }}</el-button>
        </div>
      </el-form>
    </el-dialog>

    <el-dialog :visible.sync="dialogVisible" :title="dialogType==='edit' ? $t('method.Shlb.dialog.edit') : $t('method.Shlb.dialog.add')" :close-on-click-modal="false">
      <el-form :model="merchant" label-width="100px" label-position="left">
        <el-form-item :label="$t('method.Shlb.label.phone')">
          <el-input v-model="merchant.cellphone" :placeholder="$t('method.Shlb.placeholder.enter_phone')" />
        </el-form-item>
        <el-form-item :label="$t('method.Shlb.label.name')">
          <el-input v-model="merchant.name" :placeholder="$t('method.Shlb.placeholder.enter_name')" />
        </el-form-item>
        <el-tooltip v-if="dialogType==='edit'" v-model="capsTooltip" content="Caps lock is On" placement="right" manual style="max-width: 282px;">
          <el-form-item :label="$t('method.Shlb.label.password')">
            <el-input
              :key="passwordType"
              auto-complete="new-password"
              ref="password"
              v-model="password"
              :type="passwordType"
              :placeholder="$t('method.Shlb.placeholder.password')"
              tabindex="2"
              autocomplete="on"
              @keyup.native="checkCapslock"
              @blur="capsTooltip = false"
              @keyup.enter.native="handleLogin"
            />
            <span class="show-pwd" @click="showPwd">
              <svg-icon :icon-class="passwordType === 'password' ? 'eye' : 'eye-open'" />
            </span>
          </el-form-item>
        </el-tooltip>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.enable_df')">
          <el-switch v-model="merchant.status_df" :active-value="1" :inactive-value="0" active-color="#13ce66" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit' && merchant.status_df" :label="$t('method.Shlb.label.df_rate')" style="max-width: 282px;">
          <el-input v-model="merchant.rate_df" :placeholder="$t('method.Shlb.placeholder.enter_df_rate')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit' && merchant.status_df" :label="$t('method.Shlb.label.single_df_amount')" style="max-width: 282px;">
          <el-input v-model="merchant.fee_df" :placeholder="$t('method.Shlb.placeholder.enter_single_df_amount')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.change_type')" style="max-width: 282px;">
          <el-select v-model="changeBalance.changeBalanceType" clearable :placeholder="$t('method.Shlb.placeholder.select_balance_type')">
            <el-option v-for="item in balanceType" :key="item.name" :label="item.label" :value="item.name" />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('method.Shlb.label.df_limit_amount_min')">
          <el-input v-model="amount_fixed_min" :placeholder="$t('method.Shlb.placeholder.df_limit_amount_min')" />
        </el-form-item>

        <el-form-item :label="$t('method.Shlb.label.df_limit_amount_max')">
          <el-input v-model="amount_fixed_max" :placeholder="$t('method.Shlb.placeholder.df_limit_amount_max')" />
        </el-form-item>

        <el-form-item v-if="dialogType==='edit' && changeBalance.changeBalanceType" :label="$t('method.Shlb.label.change_amount')" style="max-width: 282px;">
          <el-input v-model="changeBalance.changeAmount" :placeholder="$t('method.Shlb.placeholder.enter_change_amount')" />
          <span style="color: red;">{{ $t('method.Shlb.warning.deduction_notice') }}</span>
        </el-form-item>
        <el-form-item v-if="dialogType==='edit' && changeBalance.changeBalanceType" :label="$t('method.Shlb.label.remark')" style="max-width: 282px;">
          <el-input v-model="changeBalance.remark" :placeholder="$t('method.Shlb.placeholder.enter_remark')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.assigned_partner')">
          <el-input v-model="merchant.target_payment" type="textarea" :placeholder="$t('method.Shlb.placeholder.enter_assigned_partner')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.ip_whitelist')">
          <el-input v-model="merchant.ip" :placeholder="$t('method.Shlb.placeholder.enter_ip_whitelist')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.df_ip_whitelist')">
          <el-input v-model="merchant.ip_df" :placeholder="$t('method.Shlb.placeholder.enter_df_ip_whitelist')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.ds_ip_blacklist')">
          <el-input v-model="merchant.ds_black_ips" :placeholder="$t('method.Shlb.placeholder.enter_ds_ip_blacklist')" />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.ds_on')">
          <el-switch v-model="merchant.ds_on" :active-value="0" :inactive-value="1" active-color="#13ce66" />
        </el-form-item>

        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.ds_userid_blacklist')">
          <el-input auto-complete="new-password" v-model="merchant.ds_black_userids" :placeholder="$t('method.Shlb.placeholder.enter_ds_userid_blacklist')"  />
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.ds_userid_on')">
          <el-switch v-model="merchant.ds_userid_on" :active-value="0" :inactive-value="1" active-color="#13ce66" />
        </el-form-item>

        <!-- <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.decimalPointCallback')">
          <el-switch v-model="merchant.decimal_amt_flag" :active-value="1" :inactive-value="0" active-color="#13ce66" />
        </el-form-item> -->

        <el-form-item v-if="dialogType==='edit'" label="Notify回调类型">
          <el-switch
            v-model="merchant.notify_callback_type"
            :active-value="1"
            :inactive-value="0"
            active-color="#13ce66"
            active-text="小数点回调"
            inactive-text="整数回调" />
          <div style="font-size: 12px; color: #999; margin-top: 4px;">
            整数回调：回调金额为整数（如100）；小数点回调：回调金额保留小数（如100.25）
          </div>
        </el-form-item>

        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.google_key')">
          <el-input v-model="merchant.gg_key" disabled style="width: 350px; margin-right: 16px;" />
          <el-button type="warning" size="small" @click="handleResetGg">{{ $t('method.Shlb.button.reset_key') }}</el-button>
        </el-form-item>
        <el-form-item v-if="dialogType==='edit'" :label="$t('method.Shlb.label.merchant_key')">
          <el-input v-model="merchant.mc_key" disabled style="width: 350px; margin-right: 16px;" />
          <el-button type="warning" size="small" @click="handleResetMerchantKey">{{ $t('method.Shlb.button.reset_key') }}</el-button>
        </el-form-item>
      </el-form>

      <div style="text-align: right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('method.Shlb.button.cancel') }}</el-button>
        <el-button type="danger" @click="confirmMerchat">{{ $t('method.Shlb.button.confirm') }}</el-button>
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
    isSafe
} from '@/utils/validate'
import {
    getOtherPay
} from '@/api/setting'
import {
    getMerchant,
    addMerchant,
    updateMerchant,
    getMerchantChannel,
    updateMerchantChannel,
    resetGgkey
} from '@/api/merchant'
import { getOtherPayOptionLabel } from '@/utils/otherpay'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Shlb',
    data() {
        return {
            merchant: {},
            merchantList: [],
            otherPayList: [],
            merchant_channel: {},
            dialogVisible: false,
            channel_dialogVisible: false,
            dialogType: 'new',
            passwordType: 'password',
            capsTooltip: false,
            password: '',
            changeBalance: {},
            balanceType: [{
                'name': 'balance',
                'label': this.$t('method.Shlb.balanceType.balance')
            },
            {
                'name': 'balance_frozen',
                'label': this.$t('method.Shlb.balanceType.balance_frozen')
            }
            ],
            order_field: 'id',
            sort: 'desc',
            formItemList: [
              { label: this.$t('method.Shlb.form.id'), type: 'input', param: 'id' },
              { label: this.$t('method.Shlb.form.cellphone'), type: 'input', param: 'cellphone' },
              { label: this.$t('method.Shlb.form.name'), type: 'input', param: 'name' },
              { label: this.$t('method.Shlb.form.pid'), type: 'input', param: 'pid' },
              { label: this.$t('method.Shlb.form.status'), type: 'select', selectOptions: [
                  { value: 0, label: this.$t('method.Shlb.form.status0.0') },
                  { value: 1, label: this.$t('method.Shlb.form.status0.1') }
                ], param: 'status'
              },
              { label: this.$t('method.Shlb.form.status_id'), type: 'select', selectOptions: [
                  { value: 0, label: this.$t('method.Shlb.form.status1.0') },
                  { value: 1, label: this.$t('method.Shlb.form.status1.1') }
                ], param: 'status_id'
              },
              { label: this.$t('method.Shlb.form.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' }
            ],
            exportData: {
              tHeader: [
                this.$t('method.Shlb.export.id'),
                this.$t('method.Shlb.export.cellphone'),
                this.$t('method.Shlb.export.name'),
                this.$t('method.Shlb.export.pid'),
                this.$t('method.Shlb.export.status'),
                this.$t('method.Shlb.export.status_id'),
                this.$t('method.Shlb.export.time_create')
              ],
              filterVal: [
                'id', 'cellphone', 'name', 'pid', 'status', 'status_id', 'time_create'
              ],
              list: [],
              filename: this.$t('method.Shlb.export.filename')
            },
            params: {},
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            },
            columnList: [
                { name: this.$t('method.payment01.ds.table.balance'), key: 'balance' }
            ],
        }
    },
    created() {
        this.getOtherPay()
        this.getData()
    },
    methods: {
          getOtherPayOptionLabel,
          /* 排序*/
          async sort_change({ column }) {
              console.log(this.columnList, column)
              this.order_field = this.columnList.find(item => item.name === column.label).key
              if (column.order === 'ascending') {
                  this.sort = 'asc'
              } else if (column.order === 'descending') {
                  this.sort = 'desc'
              } else {
                  this.order_field = 'id'
                  this.sort = 'desc'
              }
              this.getData()
          },
        /* 获取数据*/
        async getData(params) {
            if (params) {
                this.params = params
            }

            var data = {
                order_field: this.order_field,
                sort: this.sort,
                serchData: this.params
            }

            // var data = {}
            data.serchData = this.params
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            const res = await getMerchant(data)
            this.merchantList = res.data
            this.paginationData.total = res.total
        },
        /* 获取三方信息*/
        async getOtherPay() {
            const res = await getOtherPay()
            this.otherPayList = res.data
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
        /* 新增商户*/
        handleAdd() {
            this.dialogType = 'new'
            this.dialogVisible = true
            this.merchant = {}
            this.password = ''
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
        /* 编辑商户*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.merchant = deepClone(scope.row)
            this.changeBalance = {}
            this.password = ''
        },
        /* 重置谷歌密钥*/
    handleResetGg() {
        this.$confirm(this.$t('method.confirm_reset_google_key'), this.$t('method.warning'), {
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel'),
            type: 'warning'
        }).then(async() => {
            var r = this.merchant.gg_key
            try {
                r = await resetGgkey({
                    'id': this.merchant.id
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.reset_success')
            })
            this.dialogVisible = false
            this.getData()
            this.merchant.gg_key = r.data
        }).catch(() => {})
    },
    /* 重置商户密钥*/
    handleResetMerchantKey() {
        this.$confirm(this.$t('method.confirm_reset_merchant_key'), this.$t('method.warning'), {
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel'),
            type: 'warning'
        }).then(async() => {
            var r = this.merchant.mc_key
            try {
                r = await resetGgkey({
                    'id': this.merchant.id,
                    'type': 'mc_key'
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.reset_success')
            })
            this.dialogVisible = false
            this.getData()
            this.merchant.gg_key = r.data
        }).catch(() => {})
    },
    /* 改变状态*/
    async changeStatus({ $index, row }, event) {
        const tipsString = row.status === 1 ? this.$t('method.confirm_disable_merchant') : this.$t('method.confirm_enable_merchant')
        this.$confirm(tipsString, this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            var data = {}
            data.id = row.id
            data.status = Math.abs(row.status - 1)
            try {
                await updateMerchant(data)
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: tipsString + this.$t('method.success')
            })
            this.getData()
        }).catch(() => {})
    },
    checkCapslock(e) {
            const {
                key
            } = e
        this.capsTooltip = key && key.length === 1 && (key >= 'A' && key <= 'Z')
    },
    showPwd() {
        if (this.passwordType === 'password') {
            this.passwordType = ''
        } else {
            this.passwordType = 'password'
        }
        this.$nextTick(() => {
            this.$refs.password.focus()
        })
    },
    /* 确认编辑通道*/
    async confirmChannel() {
        this.channel_dialogVisible = false
        var data = {}
        data.id = this.merchant.id
        this.merchant_channel.forEach(item => {
            console.log(item)
        })
        data.merchant_channel = this.merchant_channel
        try {
            await updateMerchantChannel(data)
        } catch (err) {
            return
        }
        this.dialogVisible = false
        this.$message({
            type: 'success',
            message: this.$t('method.save_success')
        })
    },
    /* 确认编辑*/
    async confirmMerchat() {
        var data = {}
        data.id = this.merchant.id
        data.cellphone = this.merchant.cellphone
        data.name = this.merchant.name
        data.target_payment = this.merchant.target_payment
        data.ip = this.merchant.ip
        data.status_df = this.merchant.status_df
        data.ip_df = this.merchant.ip_df
        data.ds_on = this.merchant.ds_on
        data.ds_black_ips = this.merchant.ds_black_ips

        data.ds_userid_on = this.merchant.ds_userid_on
        data.ds_black_userids = this.merchant.ds_black_userids

        data.amount_fixed = Number(this.merchant.amount_fixed)
        data.amount_fixed_max = Number(this.merchant.amount_fixed_max)

        // 添加小数点回调标志
        data.decimal_amt_flag = this.merchant.decimal_amt_flag
        console.log('Sending merchant update with decimal_amt_flag:', data.decimal_amt_flag)

        // 添加Notify回调类型
        data.notify_callback_type = this.merchant.notify_callback_type || 0  // 默认为0（整数回调）
        console.log('Sending merchant update with notify_callback_type:', data.notify_callback_type)

        if (data.amount_fixed > 0 && data.amount_fixed_max > 0) {
            if (data.amount_fixed > data.amount_fixed_max) {
                this.$message({
                    type: 'warning',
                    message: this.$t('method.df_min_max')
                })
                return
            }
        }

        // 代付
        if (data.status_df) {
            if (!this.merchant.rate_df || !this.merchant.fee_df) {
                this.$message({
                    type: 'warning',
                    message: this.$t('method.enter_payment_rate_fee')
                })
                return
            } else {
                data.rate_df = this.merchant.rate_df
                data.fee_df = this.merchant.fee_df
            }
        }
        // 密码
        if (this.password) {
            var message = ''
            if (this.password.length < 6) {
                message = this.$t('method.password_min_length')
            } else if (!isSafe(this.password)) {
                message = this.$t('method.no_illegal_characters')
            }
            if (message) {
                this.$message({
                    type: 'warning',
                    message: message
                })
                return
            }
            data.password = this.password
        }
        if (this.dialogType === 'edit') {
                if (this.changeBalance && this.changeBalance.changeBalanceType && this.changeBalance
                    .changeAmount) {
                if (this.changeBalance.remark) {
                    data.changeBalance = this.changeBalance
                } else {
                    this.$message({
                        type: 'warning',
                        message: this.$t('method.enter_remarks')
                    })
                    return
                }
            }
            try {
                await updateMerchant(data)
            } catch (err) {
                return
            }
        } else {
            try {
                await addMerchant(data)
            } catch (err) {
                return
            }
        }
        const { id, name } = this.merchant
        this.dialogVisible = false
        this.$notify({
            title: this.$t('method.save_success'),
            dangerouslyUseHTMLString: true,
            message: `
                <div>${this.$t('method.ID')}: ${id}</div>
                <div>${this.$t('method.name')}: ${name}</div>
            `,
            type: 'success'
        })
        this.getData()
    }
  },
    computed: {
        amount_fixed_min: {
            get() {
                var value = this.merchant.amount_fixed;
                if (value == null || value == 'null' || value == '') value = 0;
                else value = Math.trunc(value);
                return value;
            },
            set(value) {
                if (isNaN(Number(value))) return;
                if (Number(this.merchant.amount_fixed_max) > 0 && Number(this.merchant.amount_fixed_max) < Number(value)) return;
                this.$set(this.merchant, 'amount_fixed', value)
            }
        },
        amount_fixed_max: {
            get() {
                var value = this.merchant.amount_fixed_max;
                if (value == null || value == 'null' || value == '') value = 0;
                else value = Math.trunc(value);
                return value;
            },
            set(value) {
                if (isNaN(Number(value))) return;
                this.$set(this.merchant, 'amount_fixed_max', value)
            }
        }
    }
}
</script>
<style>
.otherpay-dropdown {
  max-width: 350px !important;
}
.otherpay-dropdown .el-select-dropdown__item {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
<style lang="scss" scoped>
    .show-pwd {
        position: absolute;
        right: 10px;
        font-size: 16px;
        cursor: pointer;
        user-select: none;
    }
</style>
