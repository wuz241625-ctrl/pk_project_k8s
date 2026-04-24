<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      show-refresh
      :form-item-list="formItemList"
      :export-data="exportData"
      @search="getData"
      @export="getData"
    />
    <el-form>
      <el-button
        type="success"
        plain
        @click="handleCopy(count.successOrder)"

      >{{ $t('method.ds.orderManagement.buttons.success') }}{{ count.successOrder }}</el-button>
      <el-button type="danger" plain @click="handleCopy(count.failOrder)">{{ $t('method.ds.orderManagement.buttons.fail') }}{{ count.failOrder }}</el-button>
      <el-button type="primary" plain @click="handleCopy(getRate())">{{ $t('method.ds.orderManagement.buttons.successRate') }}{{ getRate() }}</el-button>
<!--      <el-button type="primary" plain @click="dialogVisible1=true">{{ $t('method.ds.orderManagement.buttons.transactionAmount') }}{{ count.amount }}</el-button>
      <el-button type="warning" plain @click="dialogVisible=true">{{ $t('method.ds.orderManagement.buttons.processing') }}{{ count.processing }}</el-button>-->
      <el-button type="primary" plain @click="getMerchantFinish()">{{ $t('method.ds.orderManagement.buttons.transactionAmount') }}{{ count.amount }}</el-button>
      <el-button type="warning" plain @click="getProcessing()">{{ $t('method.ds.orderManagement.buttons.processing') }}{{ count.processing }}</el-button>
      <el-button
        type="warning"
        plain
        @click="handleCopy(count.processing_amount)"
      >{{ $t('method.ds.orderManagement.buttons.processingAmount') }} {{ count.processing_amount }}</el-button>
      <el-button type="primary" plain @click="handleCopy(count.realpay)">{{ $t('method.ds.orderManagement.buttons.merchantSettlement') }}{{ count.realpay }}</el-button>
      <el-button type="primary" plain @click="handleCopy(count.earn_merchant)">{{ $t('method.ds.orderManagement.buttons.merchantCommission') }}{{ count.earn_merchant }}</el-button>
      <el-button type="primary" plain @click="handleCopy(count.earn_partner)">{{ $t('method.ds.orderManagement.buttons.partnerCommission') }}{{ count.earn_partner }}</el-button>
      <el-button type="primary" plain @click="handleCopy(count.earn_system)">{{ $t('method.ds.orderManagement.buttons.platformProfit') }}{{ count.earn_system }}</el-button>
      <el-button type="primary" plain @click="handleCopy(count.stat_1003)">{{ count.stat_1003 }}</el-button>
    </el-form>
    <el-table
      :data="orderList"
      style="margin-top:6px;"
      stripe
      border
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      v-horizontal-scroll="'always'"
    >
      <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.orderId')" width="200">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="left" :label="$t('method.ds.orderManagement.table.merchantId')" width="200" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.merchant_code }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.amount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.status')">
        <template slot-scope="scope">
          <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
            {{ statusType.find(item => item.id === scope.row.status).name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.merchantId')">
        <template slot-scope="scope">
          {{ scope.row.merchant_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.channel')">
        <template slot-scope="scope">
          {{ scope.row.channel_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.code')">
        <template slot-scope="scope">
          {{ scope.row.auth_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.utr')" width="120">
        <template slot-scope="scope">
          {{ scope.row.utr }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.trans_id')" width="120">
        <template slot-scope="scope">
          {{ scope.row.trans_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.partnerId')">
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.paymentId')">
        <template slot-scope="scope">
          {{ scope.row.payment_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.upi')" width="100" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.upi }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.createTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center"
      :label="$t('method.ds.orderManagement.table.acceptTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_accept }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.paymentTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_payed }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.successTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_success }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.settlementAmount')">
        <template slot-scope="scope">
          {{ scope.row.realpay }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.merchantRate')">
        <template slot-scope="scope">
          {{ scope.row.merchant_rate }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.poundage')">
        <template slot-scope="scope">
          {{ scope.row.poundage }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.merchantCommission')">
        <template slot-scope="scope">
          {{ scope.row.earn_merchant }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.partnerTotalCommission')" width="100">
        <template slot-scope="scope">
          {{ scope.row.earn_partner }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.platformProfit')">
        <template slot-scope="scope">
          {{ scope.row.earn_system }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.userIP')">
        <template slot-scope="scope">
          {{ scope.row.player_ip }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.third_party_id')" width="100" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.third_party_name }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.third_party_order_number')" width="100" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.third_party_order_number }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.user_id')" width="100" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.user_id }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.ds.orderManagement.table.count_statics')" width="100" show-overflow-tooltip>
        <template slot-scope="scope">
          {{ scope.row.count_statics }}
        </template>
      </el-table-column>

      <el-table-column fixed="right" align="center" :label="$t('method.ds.orderManagement.table.operation')" width="120">
        <template slot-scope="scope">
          <el-button
            v-if="scope.row.status === 3"
            type="primary"
            size="mini"
            @click="handleNotify(scope)"
            style="margin-top:10px;"
          >{{ $t('method.ds.orderManagement.table.manualCallback') }}</el-button>
          <el-button
            v-if="[1,2,-1].indexOf(scope.row.status) !== -1 && scope.row.partner_id !== null"
            type="danger"
            size="mini"
            @click="handleOrderView(scope)"
            style="margin-top:10px;"
          >{{ $t('method.ds.orderManagement.table.orderCorrection') }}</el-button>


          <el-button
            v-if="[1,2,-1].indexOf(scope.row.status) !== -1"
            type="danger"
            size="mini"
            @click="handleOrderFromThird(scope)"
            style="margin-top:10px;"
          >三方补单</el-button>

          <el-button type="primary" size="small" @click="addCdView(scope)" style="margin-top:10px;">查单</el-button>
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

    <el-dialog :visible.sync="dialogVisible" :title="$t('method.ds.orderManagement.dialog.processingOrders')" >
      <el-table
        :data="merchant_processings"
        stripe
        style="width: 100%; margin-top: 30px;"
        border
        :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      >
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.merchantId')" width="240">
          <template slot-scope="scope">
            {{ scope.row.merchant_id }}
          </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.processingOrders')" sortable prop="cnt" />
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.total')" sortable prop="total" />
      </el-table>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('method.ds.orderManagement.dialog.back') }}</el-button>
      </div>
    </el-dialog>


    <el-dialog :visible.sync="dialogVisible1" :title="$t('method.ds.orderManagement.dialog.finishOrders')" >
      <el-table
        :data="merchant_finish"
        stripe
        style="width: 100%; margin-top: 30px;"
        border
        :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      >
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.merchantId')" width="240">
          <template slot-scope="scope">
            {{ scope.row.merchant_id }}
          </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.finishOrders')" sortable prop="cnt" />
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.total')" sortable prop="total" />
      </el-table>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible1=false">{{ $t('method.ds.orderManagement.dialog.back') }}</el-button>
      </div>
    </el-dialog>


  <el-dialog :visible.sync="dialogVisibleEdit" title="查单" :close-on-click-modal="false" :style="{ width: '150%', left: '-15%' }">
    <el-form label-width="115px" label-position="left">

        <el-form-item :label="$t('method.successRate.phone')"  class="form-item">
          <el-input size="small" v-model="utr" :placeholder="$t('method.enter_phone')" width="100" :style="{ width: '300px' }"/>
        </el-form-item>

    </el-form>

    <div style="text-align:right;">
      <el-button type="primary" @click="dialogVisibleEdit=false">{{ $t('method.Mslb.buttons.cancel') }}</el-button>
      <el-button type="danger" @click="addCd">{{ $t('method.Mslb.buttons.confirm') }}</el-button>
    </div>
  </el-dialog>

  <el-dialog
    :title="$t('method.supplement_order')"
    :visible.sync="dialogVisibleUtr"
    width="30%">
    <el-form :model="formData" ref="orderForm">
        <el-form-item :label="$t('method.enter_phone')" prop="utr" required>
            <el-input v-model="formData.utr"></el-input>
        </el-form-item>
        <el-form-item :label="$t('method.enter_trx') + ' (' + $t('method.optional') + ')'" prop="trans_id">
            <el-input v-model="formData.trans_id"></el-input>
        </el-form-item>
    </el-form>
    <span slot="footer" class="dialog-footer">
        <el-button @click="dialogVisibleUtr = false">{{ $t('method.cancel') }}</el-button>
        <el-button type="primary" @click="submitOrder">{{ $t('method.confirm') }}</el-button>
    </span>
</el-dialog>

  </div>
</template>

<script>
import {
    getOrderds,
    handleOrder,
    handleNotifyds,
    addDsToCd,
    handleOrderFromThird as apiHandleOrderFromThird,
    getDSMerchantFinishOrProcessing
} from '@/api/order'
import { deepClone } from '@/utils'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Dsdd',
    data() {
        return {
            utr: '',
            code: '',
            dialogVisibleEdit: false,
            dialogVisibleUtr: false,
            formData: {
                utr: '',
                trans_id: ''
            },
            merchant_finish_: false,
            processing_: false,
            count: {
                failOrder: 0,
                successOrder: 0,
                rate: 0,
                processing: 0,
                amount: 0,
                realpay: 0,
                earn_merchant: 0,
                earn_partner: 0,
                earn_system: 0,
                stat_1003: 0
            },
            orderList: [],
            params: {},
            formItemList: [
    {
        label: this.$t('method.ds.form.id'),
        type: 'input',
        param: 'code'
    },
    {
        label: this.$t('method.ds.form.merchant_code'),
        type: 'input',
        param: 'merchant_code'
    },
    {
        label: this.$t('method.ds.form.channel'),
        type: 'input',
        param: 'channel_code'
    },
    {
        label: this.$t('method.ds.form.merchant_id'),
        type: 'input',
        param: 'merchant_id'
    },
    {
        label: this.$t('method.ds.form.partner_id'),
        type: 'input',
        param: 'partner_id'
    },
    {
        label: this.$t('method.ds.form.bank_id'),
        type: 'input',
        param: 'payment_id'
    },
    {
        label: this.$t('method.ds.form.code'),
        type: 'input',
        param: 'auth_code'
    },
    {
        label: this.$t('method.ds.form.utr'),
        type: 'input',
        param: 'utr'
    },
    {
        label: this.$t('method.ds.form.trans_id'),
        type: 'input',
        param: 'trans_id'
    },
    {
        label: this.$t('method.ds.form.upi'),
        type: 'input',
        param: 'upi'
    },
    {
        label: this.$t('method.ds.form.player_ip'),
        type: 'input',
        param: 'player_ip'
    },
    {
        label: this.$t('method.ds.form.amount'),
        type: 'input',
        param: 'amount'
    },
    {
        label: this.$t('method.ds.form.status'),
        type: 'select',
        selectOptions: [],
        param: 'status'
    },
    {
        label: this.$t('method.df.form.amount_range'),
        type: 'input',
        param: 'amount_range_new'
    },
    // {
    //     label: this.$t('method.df.form.amount_range'),
    //     type: 'select',
    //     selectOptions: [
    //         { value: 1, label: this.$t('method.df.form.range_500') },
    //         { value: 2, label: this.$t('method.df.form.range_500_1000') },
    //         { value: 3, label: this.$t('method.df.form.range_1000_2000') },
    //         { value: 4, label: this.$t('method.df.form.range_2000_5000') },
    //         { value: 5, label: this.$t('method.df.form.range_5000_20000') },
    //         { value: 6, label: this.$t('method.df.form.range_20000_50000') },
    //         { value: 7, label: this.$t('method.df.form.range_above_50000') }

    //     ],
    //     param: 'amount_range'
    // },
    {
      label: this.$t('method.ds.form.time_create'),
      type: 'dateTimePicker',
      param: 'time_create',
      pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
    },
    {
      label: this.$t('method.ds.form.time_success'),
      type: 'dateTimePicker',
      param: 'time_success',
      pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
    },
    {
        label: this.$t('method.ds.form.top_partner_id'),
        type: 'input',
        param: 'top_partner_id'
    },
    {
        label: this.$t('method.ds.form.third_party_id'),
        type: 'input',
        param: 'third_party_name'
    },
    {
        label: this.$t('method.ds.form.third_party_order_number'),
        type: 'input',
        param: 'third_party_order_number'
    },
    {
        label: this.$t('method.ds.orderManagement.table.user_id'),
        type: 'input',
        param: 'user_id'
    }
],
statusType: [
    {
        id: 0,
        name: this.$t('method.ds.statusType.dispatching'),
        type: 'warning'
    },
    {
        id: 1,
        name: this.$t('method.ds.statusType.pending_payment'),
        type: 'danger'
    },
    {
        id: 2,
        name: this.$t('method.ds.statusType.pending_confirmation'),
        type: 'danger'
    },
    {
        id: 3,
        name: this.$t('method.ds.statusType.callback'),
        type: 'primary'
    },
    {
        id: 4,
        name: this.$t('method.ds.statusType.completed'),
        type: 'success'
    },
    {
        id: -1,
        name: this.$t('method.ds.statusType.cancelled'),
        type: 'info'
    },
    {
        id: 5,
        name: this.$t('method.ds.statusType.processing'),
        type: 'danger'
    }
],
exportData: {
    tHeader: [
        this.$t('method.ds.export.order_id'),
        this.$t('method.ds.export.merchant_code'),
        this.$t('method.ds.export.channel'),
        this.$t('method.ds.export.amount'),
        this.$t('method.ds.export.status'),
        this.$t('method.ds.export.merchant_id'),
        this.$t('method.ds.export.auth_code'),
        this.$t('method.ds.export.utr'),
        this.$t('method.ds.export.partner_id'),
        this.$t('method.ds.export.payment_id'),
        this.$t('method.ds.export.time_create'),
        this.$t('method.ds.export.time_accept'),
        this.$t('method.ds.export.time_payed'),
        this.$t('method.ds.export.time_success'),
        this.$t('method.ds.export.realpay'),
        this.$t('method.ds.export.merchant_rate'),
        this.$t('method.ds.export.poundage'),
        this.$t('method.ds.export.earn_merchant'),
        this.$t('method.ds.export.earn_partner'),
        this.$t('method.ds.export.earn_system'),
        this.$t('method.ds.export.player_ip'),
        this.$t('method.ds.orderManagement.table.third_party_id'),
        this.$t('method.ds.orderManagement.table.third_party_order_number'),
        this.$t('method.ds.orderManagement.table.user_id'),
        this.$t('method.ds.form.trans_id'),
        this.$t('method.ds.orderManagement.table.count_statics'),
    ],
    filterVal: [
        'code', 'merchant_code', 'channel_code', 'amount', 'status', 'merchant_id', 'auth_code',
        'utr', 'partner_id', 'payment_id', 'time_create', 'time_accept', 'time_payed', 'time_success',
        'realpay', 'merchant_rate', 'poundage', 'earn_merchant', 'earn_partner', 'earn_system', 'player_ip', 'third_party_name', 'third_party_order_number', 'user_id', 'trans_id', 'count_statics'
    ],
    list: [],
    filename: this.$t('method.ds.export.filename')
},
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            dialogVisible: false,
            dialogVisible1: false,
            // 处理中的商户订单量
            merchant_processings: [],
            merchant_finish: []
        }
    },
    created() {
        this.statusType.forEach(statusType => {
                this.formItemList.find(item => item.type === 'select').selectOptions.push({
                    value: statusType.id,
                    label: statusType.name
                })
            })
        this.getData()
    },
    methods: {
        handleOrderView(scope) {
          this.currentCode = scope.row.code;
          this.formData.utr = scope.row.utr;
          this.formData.trans_id = scope.row.trans_id;
          this.dialogVisibleUtr = true;
        },
        async submitOrder() {
          this.$refs.orderForm.validate(async (valid) => {
              if (valid) {
                  try {
                      await handleOrder({
                          'code': this.currentCode,
                          'utr': this.formData.utr,
                          'trans_id': this.formData.trans_id
                      });
                      this.$message({
                          type: 'success',
                          message: this.$t('method.order_success')
                      });
                      this.getData();
                      this.dialogVisibleUtr = false; // Close the dialog on success
                  } catch (err) {
                      // Do nothing or handle the error
                  }
              }
          });
      },
        addCdView(scope) {
          this.utr = scope.row.utr
          this.code = scope.row.code
          this.dialogVisibleEdit = true
        },
        /* 编辑码商*/
        async addCd() {
          try {
                await addDsToCd({
                    'code': this.code,
                    'utr': this.utr
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: '添加查单成功'
            })

            this.dialogVisibleEdit = false
            this.getData()
        },
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
            // 去掉首尾空格
            // const input = this.params.amount_range_new.trim();
            const input = (this.params.amount_range_new || '').trim();
            // 空值逻辑
            if (input) {
                // 检查格式是否符合 "数字-数字"
                if (!/^\d+-\d+$/.test(input)) {
                  this.$message({
                    type: 'warning',
                    message: '输入格式不正确，请使用类似 11-22 的格式',
                  });
                  return;
                }

                // 分割成两个数字
                const [min, max] = input.split('-').map(Number);

                // 检查两个数字是否有效
                if (min <= 0 || max <= 0) {
                  this.$message({
                    type: 'warning',
                    message: '金额必须大于 0',
                  });
                  return;
                }

                if (min >= max) {
                  this.$message({
                    type: 'warning',
                    message: '范围的后一个数字必须大于前一个数字',
                  });
                  return;
                }
            }
            if(this.merchant_finish_ || this.processing_){
                if(this.merchant_finish_){
                    data.merchant_finish = 1;
                }else {
                    data.processing = 1;
                }
                this.merchant_finish_ = false;
                this.processing_ = false;
                const res = await getDSMerchantFinishOrProcessing(data)
                if (isExport) {
                    this.exportData.list = res.data
                    this.$refs.search.exportExcel()
                } else {
                    this.merchant_processings = res.merchant_processing?.map(item => ({
                            ...item,
                            total: +(item.total || 0)
                        })) || []
                    this.merchant_finish = res.merchant_finish?.map(item => ({
                            ...item,
                            total: +(item.total || 0)
                        })) || []
                }
            }else {
                const res = await getOrderds(data)
                if (isExport) {
                  this.exportData.list = res.data
                  this.$refs.search.exportExcel()
                } else {
                  this.orderList = res.data
                  this.count = res.count
                  this.merchant_processings = res.merchant_processing?.map(item => ({
                    ...item,
                    total: +(item.total || 0)
                  })) || []
                  this.merchant_finish = res.merchant_finish?.map(item => ({
                    ...item,
                    total: +(item.total || 0)
                  })) || []
                  this.paginationData.total = res.total
                }
            }
        },

        /* 获取数据*/
        async getMerchantFinish() {
            this.merchant_finish_ = true;
            this.getData()
            this.dialogVisible1 = true
        },

        async getProcessing() {
            this.processing_ = true;
            this.getData()
            this.dialogVisible = true
        },

        /* 计算成功率 */
        getRate() {
            var orders = this.count.failOrder + this.count.successOrder
            if (orders) {
                return (this.count.successOrder / orders * 100).toFixed(4) + '%'
            }
            return '0%'
        },
         /* 点击复制 */
    handleCopy(amount) {
        const oInput = document.createElement('input')
        oInput.value = amount
        document.body.appendChild(oInput)
        oInput.select() // 选择对象;
        document.execCommand('Copy') // 执行浏览器复制命令
        this.$message({
            type: 'success',
            message: this.$t('method.copy_success')
        })
    },
    /* 补单 */
    async handleOrderFromThird(scope) {
      const { value, action } = await this.$prompt(this.$t('method.enter_phone'), this.$t('method.supplement_order'), {
        type: 'warning',
        confirmButtonText: this.$t('method.confirm'),
        inputPattern: /\S+/,
        inputErrorMessage: this.$t('method.phone_required'),
        cancelButtonText: this.$t('method.cancel')
      }).catch(() => ({ action: 'cancel' }));

      if (action === 'cancel') {
        return;
      }
      const trimmedUtr = value.trim();
      try {
        await apiHandleOrderFromThird({
          'code': scope.row.code,
          'utr': trimmedUtr
        });
        this.$message({
          type: 'success',
          message: this.$t('method.order_success')
        });
        this.getData();
      }
      catch (err) {
        console.error(err);
      }
    },
    /* 补单 */
    handleOrder(scope) {
        this.$prompt(this.$t('method.enter_utr'), this.$t('method.supplement_order'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async({
            value
        }) => {
            try {
                await handleOrder({
                    'code': scope.row.code,
                    'utr': value
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.order_success')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 代付手动回调 */
    async handleNotify(scope) {
        try {
            await handleNotifyds({
                'code': scope.row.code
            })
        } catch (err) {
            return
        }
        this.$message({
            type: 'success',
            message: this.$t('method.operation_successful')
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
    }
  }
}
</script>
