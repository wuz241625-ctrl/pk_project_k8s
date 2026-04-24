<template>
  <div class="app-container">
    <el-button
      :type="paymentServiceState === 1 ? 'success' : 'info'"
      @click="switchPaymentServiceState">
      {{$t('tdsz.paymentServiceState')}}: {{ paymentServiceState === 1 ? $t('tdsz.paymentServiceStateOn') : $t('tdsz.paymentServiceStateOff') }}
    </el-button>
    <el-button
      :type="jazzCashPayoutServiceState === 1 ? 'success' : 'info'"
      @click="switchJazzCashPayoutServiceState">
      {{$t('tdsz.jazzCashPayoutServiceState')}}: {{ jazzCashPayoutServiceState === 1 ? $t('tdsz.jazzCashPayoutServiceStateOn') : $t('tdsz.jazzCashPayoutServiceStateOff') }}
    </el-button>
    <el-button type="primary" @click="getData">{{ $t('tdsz.searchButton')}}</el-button>
    <el-button type="primary">{{ $t('tdsz.total') + '：' + channelList.length }}</el-button>
    <el-button type="primary" @click="handleTest">{{ $t('tdsz.orderTest') }}</el-button>
    <el-table :data="channelList" style="width: 100%;margin-top:30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('tdsz.gatewayNumber')">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('tdsz.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('tdsz.merchantRate')">
        <template slot-scope="scope">
          {{ scope.row.rate }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('tdsz.is_show_qr')">
        <template slot-scope="scope">
          {{ scope.row.is_show_qr === 1 ? $t('tdsz.yes') : $t('tdsz.no') }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('tdsz.hierarchyRate')" width="300px;">
        <template slot-scope="scope">
          {{ scope.row.rates }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('tdsz.quota')">
        <template slot-scope="scope">
          {{ scope.row.fixed === 1 ? scope.row.amount_fixed : parseInt(scope.row.amount_min) + '~' + parseInt(scope.row.amount_max) }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('tdsz.actions')" width="300px">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('tdsz.edit') }}</el-button>
          <el-button :type="scope.row.status===0 ? 'warning' : 'success'" size="small" @click="changeStatus(scope)">
            {{ scope.row.status === 1 ? $t('tdsz.close') : $t('tdsz.enable') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="$t('tdsz.edit')" :close-on-click-modal="false">
      <el-form :model="channel" label-width="80px" label-position="left">
        <el-form-item :label="$t('tdsz.gatewayNumber')">
          <el-input v-model="channel.code" :placeholder="$t('tdsz.enterAccount')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.name')">
          <el-input v-model="channel.name" :placeholder="$t('tdsz.enterName')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.merchantRate')">
          <el-input v-model="channel.rate" :placeholder="$t('tdsz.enterMerchantRate')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.is_show_qr')">
          <el-switch v-model="channel.is_show_qr" :active-value="1" :inactive-value="0" active-color="#13ce66" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.hierarchyRate')">
          <el-input v-model="channel.rates" :placeholder="$t('tdsz.enterHierarchyRate')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.fixedAmount')">
          <el-switch v-model="channel.fixed" :active-value="1" :inactive-value="0" active-color="#13ce66" />
        </el-form-item>
        <el-form-item v-show="channel.fixed === 1" :label="$t('tdsz.fixedAmount')">
          <el-input v-model="channel.amount_fixed" :placeholder="$t('tdsz.enterFixedAmount')" />
        </el-form-item>
        <el-form-item v-show="channel.fixed === 0" :label="$t('tdsz.minAmount')" style="max-width: 282px;">
          <el-input v-model="channel.amount_min" :placeholder="$t('tdsz.enterMinAmount')" />
        </el-form-item>
        <el-form-item v-show="channel.fixed === 0" :label="$t('tdsz.maxAmount')" style="max-width: 282px;">
          <el-input v-model="channel.amount_max" :placeholder="$t('tdsz.enterMaxAmount')" />
        </el-form-item>
        <!-- <el-form-item :label="$t('tdsz.hasDecimal')">
          <el-switch v-model="channel.decimal_callback_enabled" :active-value="1" :inactive-value="0" active-color="#13ce66" />
        </el-form-item> -->
        <el-form-item v-if="isDecimalCallBackChannelCode(channel.code)" :label="$t('tdsz.decimalRange')">
          <el-input-number v-model="channel.decimal_min" controls-position="right" :step-strictly="true" :step="0.01" :min="getDecimalRange(channel.code).decimalMin" :max="channel.decimal_max != null ? (channel.decimal_max * 1 - 0.01):getDecimalRange(channel.code).decimalMax - 0.01"></el-input-number>~
          <el-input-number v-model="channel.decimal_max" controls-position="right" :step-strictly="true" :step="0.01" :min="channel.decimal_min != null ? (channel.decimal_min  * 1 + 0.01):getDecimalRange(channel.code).decimalMin + 0.01" :max="getDecimalRange(channel.code).decimalMax"></el-input-number>
        </el-form-item>
        <el-form-item :label="$t('tdsz.selectThirdParty')">
          <el-select v-model="otherpay" clearable :placeholder="$t('tdsz.selectThirdParty')" popper-class="otherpay-dropdown" style="width: 280px;">
            <el-option
              v-for="_otherpay in otherPayList"
              :key="_otherpay.id"
              :label="getOtherPayOptionLabel(_otherpay)"
              :value="_otherpay.id"
            />
          </el-select>
          <el-button style="margin-left: 16px;" type="warning" size="small" @click="handleChangeOtherpay">{{ $t('tdsz.switchAll') }}</el-button>
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible = false">{{ $t('tdsz.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('tdsz.confirm') }}</el-button>
      </div>
    </el-dialog>

    <el-dialog :visible.sync="dialogVisibleTest" :title="$t('tdsz.test')" :close-on-click-modal="false">
      <el-form :model="testOrder" label-width="80px" label-position="left">
        <el-form-item :label="$t('tdsz.merchant')" style="max-width: 282px;">
          <el-input v-model="testOrder.merchant_id" :placeholder="$t('tdsz.enterMerchant')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.channel')">
          <el-select v-model="testOrder.channel_code" :placeholder="$t('tdsz.selectChannel')">
            <el-option
              v-for="i in channelList"
              :key="i.code"
              :label="i.name"
              :value="i.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('tdsz.ip')" style="max-width: 282px;">
          <el-input v-model="testOrder.ip" :placeholder="$t('tdsz.ip')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.user_id')" style="max-width: 282px;">
          <el-input v-model="testOrder.user_id" :placeholder="$t('tdsz.user_id')" />
        </el-form-item>
        <el-form-item :label="$t('tdsz.amount')" style="max-width: 282px;">
          <el-input v-model="testOrder.amount" :placeholder="$t('tdsz.enterAmount')" />
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisibleTest = false">{{ $t('tdsz.close') }}</el-button>
        <el-button type="danger" @click="confirmTest">{{ $t('tdsz.placeOrder') }}</el-button>
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
import { deepClone } from '@/utils'
import {getOtherPay, getChannel, updateChannel, testOrder, changeOtherPay} from '@/api/setting'
import {switchPaymentServiceState, getPaymentServiceState, switchJazzCashPayoutServiceState, getJazzCashPayoutServiceState} from '@/api/setting'
import { getOtherPayOptionLabel } from '@/utils/otherpay'

const defaultordertest = {
    merchant_id: '',
    channel_code: '',
    amount: ''
}

const decimalRange = {
    default: {decimalMin: -0.99, decimalMax: 0.99}
}

const decimalCallBackChannelCodes = [1005];

export default {
    data() {
        return {
            channel: '',
            testOrder: Object.assign({}, defaultordertest),
            paymentServiceState: 0,
            channelList: [],
            otherPayList: [],
            otherpay: '',
            dialogVisible: false,
            dialogVisibleTest: false,
            paginationData: {
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
    getOtherPayOptionLabel,
    /* 获取数据 */
    async getData() {
        const data = { 'size': this.paginationData.size, 'page': this.paginationData.page };
        let res = null;
        res = await getPaymentServiceState();
        this.paymentServiceState = res.data;
        res = await getJazzCashPayoutServiceState();
        this.jazzCashPayoutServiceState = res.data;
        res = await getOtherPay();
        this.otherPayList = res.data;
        this.otherPayList.unshift({ id: 0, name: this.$t('method.data.getAllCancel') });
        res = await getChannel(data);
        this.channelList = res.data;
        this.paginationData.total = res.total;
    },
    /* 改变全局代付开关状态 */
    switchPaymentServiceState() {
        const isOn = this.paymentServiceState === 1  // ← 指向 data 里的 paymentServiceState
        const tipsString = isOn
            ? '关闭后将停止所有代收代付业务，请确认是否继续？'
            : '开启后将恢复代收代付业务，请确认是否继续？'
        const titleString = '收付总开关'

        this.$confirm(tipsString, titleString, {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            try {
                await switchPaymentServiceState({});
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: '操作成功',
            })
            this.getData()
        }).catch(() => {})
    },
    /* 改变全局代付开关状态 */
    switchJazzCashPayoutServiceState() {
        const isOn = this.paymentServiceState === 1  // ← 指向 data 里的 paymentServiceState
        const tipsString = isOn
            ? '关闭后将单独停止JazzCash代付业务，请确认是否继续？'
            : '开启后将恢复JazzCash代付业务，请确认是否继续？'
        const titleString = 'JazzCash代付业务单独控制'

        this.$confirm(tipsString, titleString, {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            try {
                await switchJazzCashPayoutServiceState({});
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: '操作成功',
            })
            this.getData()
        }).catch(() => {})
    },

    /* 编辑下单 */
    handleTest(scope) {
        this.dialogVisibleTest = true;
        this.testOrder = Object.assign({}, defaultordertest);
    },

    /* 编辑通道 */
    handleEdit(scope) {
        this.dialogVisible = true;
        this.checkStrictly = true;
        this.channel = deepClone(scope.row);
        this.otherpay = '';
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

    /* 开启关闭 */
    changeStatus({ $index, row }, event) {
        const tipsString = row.status === 1 ? this.$t('method.status.close') : this.$t('method.status.open');
        this.$confirm(this.$t('method.status.confirmChange') + tipsString + this.$t('method.status.channel'), this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async () => {
            const data = { id: row.id, status: Math.abs(row.status - 1) };
            try { await updateChannel(data); } catch (err) { return; }
            this.$message({
                type: 'success',
                message: tipsString + this.$t('method.status.success')
            });
            this.getData();
        }).catch(() => {});
    },

    /* 一键全切 */
    handleChangeOtherpay() {
        this.$confirm(this.$t('method.changeAll.confirmSwitch'), this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async () => {
            const data = { 'code': this.channel.code, 'otherpay': this.otherpay };
            try { await changeOtherPay(data); } catch (err) { return; }
            this.$message({
                type: 'success',
                message: this.$t('method.changeAll.success')
            });
            this.getData();
        }).catch(() => {});
    },

    /* 确认保存 */
    async confirmRole() {
        const data = this.channel;
        try { await updateChannel(data); } catch (err) { return; }
        const { code, name } = this.channel;
        this.dialogVisible = false;
        this.$notify({
            title: this.$t('method.save.successTitle'),
            dangerouslyUseHTMLString: true,
            message: `
                <div>${this.$t('method.save.gatewayCode')}: ${code}</div>
                <div>${this.$t('method.save.channelName')}: ${name}</div>
            `,
            type: 'success'
        });
        this.getData();
    },

    /* 下单测试 */
    async confirmTest() {
        if (!this.testOrder.amount || !this.testOrder.channel_code || !this.testOrder.merchant_id) {
            this.$message({
                type: 'warning',
                message: this.$t('method.testOrder.incompleteInfo')
            });
        } else {
            let res = {};
            try { res = await testOrder(this.testOrder); } catch (err) { return; }
            this.$message({
                type: 'success',
                message: this.$t('method.testOrder.success')
            });
            if (res.data) {
                window.open(res.data);
            }
        }
    },
    getDecimalRange(channelCode) {
        return decimalRange[channelCode] || decimalRange.default;
    },
    isDecimalCallBackChannelCode(channelCode) {
        return decimalCallBackChannelCodes.includes(channelCode);
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
