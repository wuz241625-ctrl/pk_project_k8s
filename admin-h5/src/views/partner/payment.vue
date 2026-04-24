<template>
    <div class="app-container">
      <baseSearch
        ref="search"
        :form-item-list="formItemList"
        :export-data="exportData"
        @search="getData"
        @export="getData"
      />
      <el-form>
        <!-- <el-button type="primary" @click="batchDisable">{{ $t('payment01.ds.buttons.batchDisable') }}</el-button> -->
        <el-button type="primary" plain @click="handleCopy(count.online_ds)">
          {{ $t('method.payment01.ds.buttons.copyCollectOnline') }}：{{ count.online_ds }}
        </el-button>
        <el-button type="primary" plain @click="handleCopy(count.online_df)">
          {{ $t('method.payment01.ds.buttons.copyPayOnline') }}：{{ count.online_df }}
        </el-button>
        <el-button type="primary" plain @click="handleAdd()">{{ $t('method.payment01.ds.buttons.add') }}</el-button>
      </el-form>
      <el-table
        :data="paymentsList"
        style="margin-top:16px;"
        border
        stripe
        :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
        @sort-change="sort_change"
      >
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.id')">
          <template slot-scope="scope">
            {{ scope.row.id }}
          </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.partnerId')" width="100">
          <template slot-scope="scope">
            {{ scope.row.partner_id }}
          </template>
        </el-table-column>
        <!-- <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.bankName')" width="100">
          <template slot-scope="scope">
            {{ bank_type.find(item => item.id === parseInt(scope.row.bank_type)) ? bank_type.find(item => item.id === parseInt(scope.row.bank_type)).name : '' }}
          </template>
        </el-table-column> -->
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.bankName')" width="100">
          <template slot-scope="scope">
            {{
              (() => {
                const bank = bank_type.find(item => item.id === parseInt(scope.row.bank_type));
                return bank ? bank.name : '';
              })()
            }}
          </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.upi')" width="200">
          <template slot-scope="scope">
            <a @click="checkUPI(scope.row.upi)">{{ scope.row.upi }}</a>
          </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.limit_info')" width="120" show-overflow-tooltip>
            <template slot-scope="scope" >
                <div class="limit_info_box" v-if="scope.row.easypaisa_limits && scope.row.bank_type == '97'">
                    <el-tooltip class="item" effect="dark" style="max-width: 100px!important;"
                                :content="
                                    `
                                `" placement="top">
                        <div slot="content">
                            {{$t('method.payment01.ds.table.debitDaily')}}：{{scope.row.easypaisa_limits.debitDaily}}&nbsp;/&nbsp;{{scope.row.easypaisa_limits.debitDailyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.debitMonthly')}}：{{scope.row.easypaisa_limits.debitMonthly}}&nbsp;/&nbsp;{{scope.row.easypaisa_limits.debitMonthlyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.creditDaily')}}：{{scope.row.easypaisa_limits.creditDaily}}&nbsp;/&nbsp;{{scope.row.easypaisa_limits.creditDailyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.creditYearly')}}：{{scope.row.easypaisa_limits.creditMonthly}}&nbsp;/&nbsp;{{scope.row.easypaisa_limits.creditMonthlyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.update_time')}}：{{scope.row.easypaisa_limits.update_time}}<br/>
                        </div>
                        <el-tag>{{$t('method.payment01.ds.table.limit_info')}}</el-tag>
                    </el-tooltip>
                </div>
                <div class="limit_info_box" v-if="scope.row.jazzcash_limits && scope.row.bank_type == '98'">
                    <el-tooltip class="item" effect="dark" style="max-width: 100px!important;"
                                :content="
                                    `
                                `" placement="top">
                        <div slot="content">
                            {{$t('method.payment01.ds.table.debitDaily')}}：{{scope.row.jazzcash_limits.debitDaily}}&nbsp;/&nbsp;{{scope.row.jazzcash_limits.debitDailyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.debitMonthly')}}：{{scope.row.jazzcash_limits.debitMonthly}}&nbsp;/&nbsp;{{scope.row.jazzcash_limits.debitMonthlyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.creditDaily')}}：{{scope.row.jazzcash_limits.creditDaily}}&nbsp;/&nbsp;{{scope.row.jazzcash_limits.creditDailyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.creditYearly')}}：{{scope.row.jazzcash_limits.creditMonthly}}&nbsp;/&nbsp;{{scope.row.jazzcash_limits.creditMonthlyThreshold}}<br/>
                            {{$t('method.payment01.ds.table.update_time')}}：{{scope.row.jazzcash_limits.update_time}}<br/>
                        </div>
                        <el-tag>{{$t('method.payment01.ds.table.limit_info')}}</el-tag>
                    </el-tooltip>
                </div>
            </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.sysBalance')" width="120">
          <template slot-scope="scope">
            {{ scope.row.sys_balance }}
          </template>
        </el-table-column>
        <el-table-column fixed="left" align="center" :label="$t('method.payment01.ds.table.balance')" sortable width="120">
          <template slot-scope="scope">
            {{ scope.row.balance }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.limit')">
          <template slot-scope="scope">
            {{ scope.row.amount_top }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.collect')">
          <template slot-scope="scope">
            <el-tag :type="scope.row.online_ds === 1 ? 'success' : 'danger'">
              {{ scope.row.online_ds === 1 ? 'Online' : 'Offline' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.pay')">
          <template slot-scope="scope">
            <el-tag :type="scope.row.online_df === 1 ? 'success' : 'danger'">
              {{ scope.row.online_df === 1 ? 'Online' : 'Offline' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column align="center" :label="$t('method.payment01.ds.table.collectionStatus')">
          <template slot-scope="scope">
            <el-tag :type="scope.row.online_status === 1 ? 'success' : 'danger'">
              {{ scope.row.online_status === 1 ? 'Collected' : 'Not Collected' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column align="center" :label="$t('method.payment01.ds.table.mobileOnline')">
          <template slot-scope="scope">
            <el-tag :type="scope.row.online_mobile_status === 1 ? 'success' : 'danger'">
              {{ scope.row.online_mobile_status === 1 ? 'Online' : 'OffLine' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column align="center" :label="$t('method.payment01.ds.table.rate')">
          <template slot-scope="scope">
            {{ scope.row.rate + '%' }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.bankAccount')" width="120">
          <template slot-scope="scope">
            {{ scope.row.account }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.bankName')" width="100" show-overflow-tooltip>
          <template slot-scope="scope">
            {{ scope.row.name }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.ifsc')" width="120">
          <template slot-scope="scope">
            {{ scope.row.ifsc }}
          </template>
        </el-table-column>
        <!-- <el-table-column align="center" :label="$t('method.payment01.ds.table.accountType')" width="120">
          <template slot-scope="scope">
            {{ account_types.find(item => item.id === scope.row.account_type).name }}
          </template>
        </el-table-column> -->
      <el-table-column align="center" :label="$t('method.payment01.ds.table.accountType')" width="120">
        <template slot-scope="scope">
          {{
            (() => {
              const accountType = account_types.find(item => item.id === scope.row.account_type);
              return accountType ? accountType.name : '';
            })()
          }}
        </template>
      </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.gmail')" show-overflow-tooltip>
          <template slot-scope="scope">
            {{ scope.row.gmail }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.gmailPw')" width="100" show-overflow-tooltip>
          <template slot-scope="scope">
            {{ scope.row.gmail_pw }}
          </template>
        </el-table-column>
        <el-table-column align="center" :label="$t('method.payment01.ds.table.createdTime')" width="160">
          <template slot-scope="scope">
            {{ scope.row.time_create }}
          </template>
        </el-table-column>
        <!-- <el-table-column align="center" :label="$t('method.payment01.ds.table.collection')" width="160">
          <template slot-scope="scope">
            {{ collection.find(item => item.id === scope.row.priority_collection).name }}
          </template>
        </el-table-column> -->
      <el-table-column align="center" :label="$t('method.payment01.ds.table.collection')" width="160">
        <template slot-scope="scope">
          {{
            (() => {
              const item = collection.find(item => item.id === scope.row.priority_collection);
              return item ? item.name : '';
            })()
          }}
        </template>
      </el-table-column>
        <el-table-column fixed="right" align="center" :label="$t('method.payment01.ds.buttons.other')" width="300">
          <template slot-scope="scope">
            <el-button type="danger" size="small" @click="cancelLimitPayment(scope)">{{ $t('method.payment01.ds.buttons.cancelLimit') }}</el-button>
            <el-button
              v-if="scope.row.balance != scope.row.sys_balance"
              type="warning"
              size="small"
              @click="handleCorrection(scope)"
            >
              {{ $t('method.payment01.ds.buttons.correction') }}
            </el-button>
            <el-button type="warning" size="small" @click="handleChangeTop(scope)">
              {{ $t('method.payment01.ds.buttons.limit') }}
            </el-button>
            <el-button
              :type="scope.row.certified==0?'warning':'success'"
              size="small"
              @click="handleChangeCertified(scope)"
            >
              {{ scope.row.certified==1 ? $t('method.payment01.ds.buttons.reject') : $t('method.payment01.ds.buttons.pass') }}
            </el-button>
            <el-button
              :type="scope.row.status==0?'warning':'success'"
              size="small"
              @click="handleChangeStatus(scope)"
            >
              {{ scope.row.status==1 ? $t('method.payment01.ds.buttons.disable') : $t('method.payment01.ds.buttons.enable') }}
            </el-button>
            <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('method.payment01.ds.buttons.delete') }}</el-button>
            <el-button
              style="margin-top: 10px"
              type="danger"
              size="small"
              @click="handleResetting(scope)"
            >
              {{ $t('method.payment01.ds.buttons.reset') }}
            </el-button>
            <el-button
              style="margin-top: 10px"
              :type="scope.row.manual_status==1?'warning':'success'"
              size="small"
              @click="handleChangeManualStatus(scope)"
            >
              {{ scope.row.manual_status==1 ? $t('method.payment01.ds.buttons.unlockManually') : $t('method.payment01.ds.buttons.lockManually') }}
            </el-button>
            <el-button
              style="margin-top: 10px"
              :type="scope.row.priority_collection==0?'warning':'success'"
              size="small"
              @click="handlePriorityCollectionStatus(scope)"
            >
              {{ scope.row.priority_collection==1 ? $t('method.payment01.ds.buttons.priorityCollection') : $t('method.payment01.ds.buttons.normalCollection') }}
            </el-button>
            <el-button type="danger" size="small" @click="handleEdit(scope)">{{ $t('method.payment01.ds.buttons.edit') }}</el-button>

             <el-button
                style="margin-top: 10px"
                v-if="scope.row.type === 0"
                :type="scope.row.monitor_status==0?'warning':'success'"
                size="small"
                @click="handleChangeMonitorStatus(scope)"
              >
              {{ scope.row.monitor_status==1 ? $t('method.payment01.ds.buttons.disable_monitor') : $t('method.payment01.ds.buttons.enable_monitor') }}
            </el-button>

            <el-button
              style="margin-top: 10px"
              :type="['warning','success'][scope.row.partner_status]"
              size="small"
              @click="changePartnerStatus(scope)"
              v-if="scope.row.type === 0"
            >
              {{ [$t('method.Mslb.table.unlock'), $t('method.Mslb.table.lock')][scope.row.partner_status] }}
           </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog :visible.sync="dialogVisible" :title="$t('method.payment01.dialog.upiTitle')" :close-on-click-modal="false">
        <div ref="qrCodeUrl" class="qrcode" />
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

      <el-dialog :visible.sync="dialogVisibleEdit" :title="$t('method.payment01.ds.dialog.editTitle')" :close-on-click-modal="false">
        <el-form :model="payment" label-width="115px" label-position="left">

          <el-row :gutter="20">
            <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.payment_id')">
                    <el-input v-model="payment.id" :disabled="true" />
                </el-form-item>
            </el-col>

            <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.bankType')">
                  <el-select v-model="selectedBankType" :placeholder="$t('method.payment01.ds.dialog.selectBankType')" filterable>
                    <el-option
                      v-for="bank in bank_type"
                      :key="bank.id"
                      :label="bank.name"
                      :value="bank.id">
                    </el-option>
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.accountType')">
                  <el-select v-model="selectedAccountType" :placeholder="$t('method.payment01.ds.dialog.selectAccountType')">
                    <el-option
                      v-for="bank in account_types"
                      :key="bank.id"
                      :label="bank.name"
                      :value="bank.id">
                    </el-option>
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.partnerId')">
                  <el-input v-model="partner_id" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.channel')">
                  <el-select v-model="channel" clearable multiple :placeholder="$t('method.payment01.ds.dialog.selectChannel')">
                    <el-option
                      v-for="item in channels"
                      :key="item.code"
                      :label="item.code + ' | ' + item.name"
                      :value="item.code"
                      :disabled="selectedChannelCodes.includes(item.code)"
                    />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.ifsc')">
                  <el-input v-model="ifsc" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.upi')">
                  <el-input v-model="upi" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.netId')">
                  <el-input v-model="net_id" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.netTradePw')">
                  <el-input v-model="net_trade_pw" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.account')">
                  <el-input v-model="account" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.name')">
                  <el-input v-model="name" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.netPw')">
                  <el-input v-model="net_pw" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.phone')">
                  <el-input v-model="phone" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.gmail')">
                  <el-input v-model="gmail" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.gmailPw')">
                  <el-input v-model="gmail_pw" />
                </el-form-item>
              </el-col>


          </el-row>

        </el-form>
        <div style="text-align:right;">
          <el-button type="primary" @click="dialogVisibleEdit=false">{{ $t('method.payment01.ds.dialog.cancel') }}</el-button>
          <el-button type="danger" @click="confirmEdit">{{ $t('method.payment01.ds.dialog.confirm') }}</el-button>
        </div>
      </el-dialog>


      <el-dialog :visible.sync="dialogVisibleAdd" :title="$t('method.payment01.ds.dialog.add')" :close-on-click-modal="false">
        <el-form :model="payment" label-width="115px" label-position="left">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.bankType')">
                  <el-select v-model="selectedBankType" :placeholder="$t('method.payment01.ds.dialog.selectBankType')" filterable>
                    <el-option
                      v-for="bank in bank_type"
                      :key="bank.id"
                      :label="bank.name"
                      :value="bank.id">
                    </el-option>
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.accountType')">
                  <el-select v-model="selectedAccountType" :placeholder="$t('method.payment01.ds.dialog.selectAccountType')">
                    <el-option
                      v-for="bank in account_types"
                      :key="bank.id"
                      :label="bank.name"
                      :value="bank.id">
                    </el-option>
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.partnerId')">
                  <el-input v-model="partner_id" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.channel')">
                  <el-select v-model="channel" clearable multiple :placeholder="$t('method.payment01.ds.dialog.selectChannel')">
                    <el-option
                      v-for="item in channels"
                      :key="item.code"
                      :label="item.code + ' | ' + item.name"
                      :value="item.code"
                    />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.ifsc')">
                  <el-input v-model="ifsc" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.upi')">
                  <el-input v-model="upi" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.netId')">
                  <el-input v-model="net_id" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.netTradePw')">
                  <el-input v-model="net_trade_pw" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.account')">
                  <el-input v-model="account" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.name')">
                  <el-input v-model="name" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.netPw')">
                  <el-input v-model="net_pw" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.phone')">
                  <el-input v-model="phone" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.gmail')">
                  <el-input v-model="gmail" />
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item :label="$t('method.payment01.ds.dialog.gmailPw')">
                  <el-input v-model="gmail_pw" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>


        <div style="text-align:right;">
          <el-button type="primary" @click="dialogVisibleAdd=false">{{ $t('method.payment01.ds.dialog.cancel') }}</el-button>
          <el-button type="danger" @click="confirmAdd">{{ $t('method.payment01.ds.dialog.confirm') }}</el-button>
        </div>
      </el-dialog>

    </div>
  </template>

  <script>
  import {
      getBank_type,
      getPayment,
      updatePayment,
      updatePaymentMonitorStatus,
      updatePaymentLimit,
      updatePaymentReject,
      updatePaymentPass,
      updatePaymentDisenable,
      updatePaymentEnable,
      updatePaymentLock,
      updatePaymentUnlock,
      updatePaymentCorrection,
      updatePaymentCommon,
      updatePaymentPri,
      updatePaymentEdit,
      addPayment,
      deletePayment,
      resettingPayment,
      batchDisablePayment,
      cancelLimit,
      getChannel,
      checkUpiPermission,
      updatePartnerLock,
      updatePartnerUnlock
  } from '@/api/partner'
  import QRCode from 'qrcodejs2'

  export default {
      name: 'Skzl',
      data() {
          return {
              selectedChannelCodes: [], // 已选中的通道代码
              count: {
                  ds_online: 0,
                  df_online: 0
              },
              paymentsList: [],
              selectedBankType: '',
              selectedAccountType: '',
              ifsc: '',
              account: '',
              name: '',
              net_id: '',
              net_pw: '',
              net_trade_pw: '',
              phone: '',
              gmail: '',
              gmail_pw: '',
              partner_id: '',
              upi: '',
              bank_type: [],
              bank_type_id: -1,
              order_field: 'id',
              sort: 'desc',
              dialogVisible: false,
              dialogVisibleEdit: false,
              dialogVisibleAdd: false,
              payment: {},
              channels: {},
              channel: null,
              upi: null,
              params: {},
              formItemList: [
      {
          label: this.$t('method.payment01.ds.form.id'),
          type: 'input',
          param: 'id'
      },
      {
          label: this.$t('method.payment01.ds.form.partnerId'),
          type: 'input',
          param: 'partner_id'
      },
      {
          label: this.$t('method.payment01.ds.form.upi'),
          type: 'input',
          param: 'upi'
      },
      {
          label: this.$t('method.payment01.ds.form.name'),
          type: 'input',
          param: 'name'
      },
      {
          label: this.$t('method.payment01.ds.form.collect'),
          type: 'select',
          param: 'collect',
          selectOptions: [
              {
                  value: 0,
                  label: this.$t('method.payment01.ds.form.offline')
              },
              {
                  value: 1,
                  label: this.$t('method.payment01.ds.form.online')
              }
          ]
      },
      {
          label: this.$t('method.payment01.ds.form.bankName'),
          type: 'select',
          filterable: true,
          param: 'bank_type',
          selectOptions: [] // 这里的选项需要从其他地方加载
      },
      {
          label: this.$t('method.payment01.ds.form.pay'),
          type: 'select',
          param: 'pay',
          selectOptions: [
              {
                  value: 0,
                  label: this.$t('method.payment01.ds.form.offline')
              },
              {
                  value: 1,
                  label: this.$t('method.payment01.ds.form.online')
              }
          ]
      },
      {
          label: this.$t('method.payment01.ds.form.type'),
          type: 'select',
          param: 'account_type',
          selectOptions: [] // 这里的选项需要从其他地方加载
      },
      {
          label: this.$t('method.payment01.ds.form.verify'),
          type: 'select',
          param: 'certified',
          selectOptions: [
              {
                  value: 0,
                  label: this.$t('method.payment01.ds.form.unverified')
              },
              {
                  value: 1,
                  label: this.$t('method.payment01.ds.form.verified')
              }
          ]
      },
      {
          label: this.$t('method.payment01.ds.form.status'),
          type: 'select',
          param: 'status',
          selectOptions: [
              {
                  value: 0,
                  label: this.$t('method.payment01.ds.form.inactive')
              },
              {
                  value: 1,
                  label: this.$t('method.payment01.ds.form.active')
              }
          ]
      },
      {
          label: this.$t('method.payment01.ds.form.manualStatus'),
          type: 'select',
          param: 'manual_status',
          selectOptions: [
              {
                  value: 0,
                  label: this.$t('method.payment01.ds.form.unlocked')
              },
              {
                  value: 1,
                  label: this.$t('method.payment01.ds.form.locking')
              }
          ]
      },
      {
          label: this.$t('method.payment01.ds.form.collection'),
          type: 'select',
          param: 'priority_collection',
          selectOptions: [
              {
                  value: 0,
                  label: this.$t('method.payment01.ds.form.ordinaryCollection')
              },
              {
                  value: 1,
                  label: this.$t('method.payment01.ds.form.priorityCollection')
              }
          ]
      },
      {
          label: this.$t('method.payment01.ds.form.channel'),
          type: 'input',
          param: 'channel'
      }
  ],

  account_types: [
      {
          id: 0,
          name: this.$t('method.payment01.ds.accountTypes.saving')
      },
      {
          id: 1,
          name: this.$t('method.payment01.ds.accountTypes.current')
      },
      {
          id: 2,
          name: this.$t('method.payment01.ds.accountTypes.corporate')
      }
  ],

  collection: [
      {
          id: 0,
          name: this.$t('method.payment01.ds.collection.normal')
      },
      {
          id: 1,
          name: this.$t('method.payment01.ds.collection.priority')
      }
  ],

  exportData: {
      tHeader: [
          this.$t('method.payment01.ds.export.id'),
          this.$t('method.payment01.ds.export.partnerId'),
          this.$t('method.payment01.ds.export.bankName'),
          this.$t('method.payment01.ds.export.upi'),
          this.$t('method.payment01.ds.export.sysBalance'),
          this.$t('method.payment01.ds.export.balance'),
          this.$t('method.payment01.ds.export.limit'),
          this.$t('method.payment01.ds.export.collect'),
          this.$t('method.payment01.ds.export.pay'),
          this.$t('method.payment01.ds.export.rate'),
          this.$t('method.payment01.ds.export.account'),
          this.$t('method.payment01.ds.export.name'),
          this.$t('method.payment01.ds.export.ifsc'),
          this.$t('method.payment01.ds.export.accountType'),
          this.$t('method.payment01.ds.export.gmail'),
          this.$t('method.payment01.ds.export.gmailPw'),
          this.$t('method.payment01.ds.export.createdTime'),
          this.$t('method.payment01.ds.export.collection')
      ],
      filterVal: [
          'id', 'partner_id', 'bank_name', 'upi', 'sys_balance', 'balance', 'amount_top',
          'online_ds', 'online_df', 'rate', 'account', 'name', 'ifsc', 'account_type', 'gmail',
          'gmail_pw', 'time_create', 'priority_collection'
      ],
      list: [],
      filename: this.$t('method.payment01.ds.export.filename')
  },
              paginationData: {
                  page: 1,
                  size: 10,
                  total: 0
              }
          }
      },
      created() {
          this.account_types.forEach(statusType => {
              this.formItemList.find(item => item.label === this.$t('method.payment01.ds.form.type')).selectOptions.push({
                  value: statusType.id,
                  label: statusType.name
              })
          })
          this.getBank();
      },
      methods: {
          async changePartnerStatus({ $index, row }) {
              const tipsString = row.partner_status === 1 ? this.$t('method.lock') : this.$t('method.unlock')
              this.$confirm(this.$t('method.confirm_action', { action: tipsString }), this.$t('method.warning'), {
                  type: 'warning',
                  confirmButtonText: this.$t('method.confirm'),
                  cancelButtonText: this.$t('method.cancel')
              }).then(async() => {
                  var data = {}
                  data.id = row.partner_id
                  data.status = row.partner_status === 1 ? 0 : 1
                  try {
                      row.partner_status === 1 ? await updatePartnerLock(data) : await updatePartnerUnlock(data)
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
          /* 获取通道channel*/
          async _getChannel(data=null) {
              const res = await getChannel()
              this.channels = res.data
              // 如果 data 存在并且包含 row.channel
              if (data && data.row && data.row.channel) {
                  this.channel = [...data.row.channel.split(',')]; // 初始化选中的通道
                  // 已选择的通道代码
                  this.selectedChannelCodes = data.row.channel.split(',').join(',');
              } else {
                  this.selectedChannelCodes = [];
                  this.channel = []; // 如果没有提供有效的 data，则初始化为空数组
              }
          },
          /* 获取银行*/
          async getBank(params) {
              const res = await getBank_type()
              this.bank_type = res.data
              this.bank_type.forEach(bankType => {
                  this.formItemList.find(item => item.label === this.$t('method.payment01.ds.form.bankName')).selectOptions.push({
                      value: bankType.id,
                      label: bankType.name
                  })
              })
              this.getData()
          },
          /* 获取数据*/
          async getData(params, isExport = false) {
              if (params) {
                  this.params = params
                  this.paginationData.page = 1
              }

              var data = {
                  order_field: this.order_field,
                  sort: this.sort,
                  serchData: this.params,
                  size: this.paginationData.size,
                  page: this.paginationData.page,
                  is_del: false
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
                  // 匹配相关的银行名字和账户类型
                  this.exportData.list.forEach((items, index) => {
                      this.exportData.list[index]['bank_name'] = this.get_type_name(items,"1")
                      this.exportData.list[index]['account_type'] = this.get_type_name(items,"2")
                  })
                  this.$refs.search.exportExcel()
              } else {
                  this.paymentsList = res.data
                  this.count = res.count
                  this.paginationData.total = res.total
              }
          },
          get_type_name(items,type){
              let bank_type_ = {}
              if(type === "1")
                  bank_type_ = this.bank_type.find(item => parseInt(items.bank_type) === item.id)
              else
                  bank_type_ = this.account_types.find(item => parseInt(items.account_type) === item.id)
              if(bank_type_){
                return bank_type_.name
              }else{
                  return ""
              }
          },
          async sort_change({
              column
          }) {
              if (column.order === 'ascending') {
                  this.order_field = 'balance'
                  this.sort = 'asc'
              } else if (column.order === 'descending') {
                  this.order_field = 'balance'
                  this.sort = 'desc'
              } else {
                  this.order_field = 'id'
                  this.sort = 'desc'
              }
              this.getData()
          },
          /* 取消限制 */
      cancelLimitPayment(scope) {
          this.$prompt(this.$t('method.cancel_limit.confirm'), this.$t('method.cancel_limit.title'), {
              type: 'warning',
              inputPlaceholder: this.$t('method.cancel_limit.placeholder'),
              inputPattern: /^(\d+(\.\d{1,2})?)?$/,
              inputErrorMessage: this.$t('method.cancel_limit.error'),
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async({ value }) => {
              try {
                  await cancelLimit({
                      id: scope.row.id,
                      hours: value
                  });
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.update_success')
              });
              this.getData();
          }).catch(() => {});
      },
      /* 删除成员 */
      handleDelete({ $index, row }) {
          this.$confirm(this.$t('method.delete.confirm'), this.$t('method.delete.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              try {
                  await deletePayment({
                      'id': row.id,
                      'is_del': false
                  });
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.delete.success')
              });
              this.getData();
          }).catch(() => {});
      },
      /* 重置成员 */
      handleResetting({ $index, row }) {
          this.$confirm(this.$t('method.reset.confirm'), this.$t('method.reset.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              try {
                  await resettingPayment({
                      'id': row.id,
                      'is_resetting': false
                  });
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.reset.success')
              });
              this.getData();
          }).catch(() => {});
      },
      /* 矫正 */
      handleCorrection({ $index, row }) {
          this.$confirm(this.$t('method.correction.confirm'), this.$t('method.correction.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              var data = {
                  id: row.id,
                  correction: 1
              };
              try {
                  await updatePaymentCorrection(data);
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.correction.success')
              });
              this.getData();
          }).catch(() => {});
      },
      /* 修改上限 */
      handleChangeTop(scope) {
          this.$prompt(this.$t('method.change_top.placeholder'), this.$t('method.change_top.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async({ value }) => {
              try {
                  await updatePaymentLimit({
                      id: scope.row.id,
                      amount_top: value
                  });
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.change_top.success')
              });
              this.getData();
          }).catch(() => {});
      },
      /* 改变认证 */
      handleChangeCertified({ $index, row }) {
          const tipsString = row.certified === 1 ? this.$t('method.certified.reject') : this.$t('method.certified.pass');
          this.$confirm(this.$t('method.certified.confirm', { status: tipsString }), this.$t('method.certified.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              var data = {
                  id: row.id,
                  certified: Math.abs(row.certified - 1)
              };
              try {
                  row.certified === 1 ? await updatePaymentReject(data) : await updatePaymentPass(data);
                  // await updatePayment(data);
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.certified.success', { status: tipsString })
              });
              this.getData();
          }).catch(() => {});
      },
      /* 改变状态 */
      handleChangeStatus({ $index, row }) {
          const tipsString = row.status === 1 ? this.$t('method.status0.disable') : this.$t('method.status0.enable');
          this.$confirm(this.$t('method.status0.confirm', { status: tipsString }), this.$t('method.status0.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              var data = {
                  id: row.id,
                  status: Math.abs(row.status - 1)
              };
              try {
                  row.status === 1 ? await updatePaymentDisenable(data) : await updatePaymentEnable(data);
                  // await updatePayment(data);
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.status.success', { status: tipsString })
              });
              this.getData();
          }).catch(() => {});
      },
      handlePriorityCollectionStatus({ row }) {
          const tipsString = row.priority_collection === 1 ? this.$t('method.priority_collection.normal') : this.$t('method.priority_collection.priority');
          this.$confirm(this.$t('method.priority_collection.confirm', { status: tipsString }), this.$t('method.priority_collection.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              var data = {
                  id: row.id,
                  priority_collection: Math.abs(row.priority_collection - 1)
              };
              try {
                row.priority_collection === 1 ? await updatePaymentCommon(data) : await updatePaymentPri(data);
                // await updatePayment(data);
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.priority_collection.success', { status: tipsString })
              });
              await this.getData();
          }).catch(() => {});
      },
      handleChangeMonitorStatus({ row }) {
          const tipsString = row.monitor_status === 1 ? this.$t('method.manual_status.disable_monitor') : this.$t('method.manual_status.enable_monitor');
          this.$confirm(this.$t('method.manual_status.confirm_monitor', { status: tipsString }), this.$t('method.manual_status.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              var data = {
                  id: row.id,
                  channel: row.channel,
                  // monitor_status: Math.abs(row.monitor_status - 1),
                  monitor_status: (typeof row.monitor_status === 'number' && (row.monitor_status === 0 || row.monitor_status === 1))
                  ? Math.abs(row.monitor_status - 1)
                  : 0

              };
              try {
                  await updatePaymentMonitorStatus(data);
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.manual_status.success', { status: tipsString })
              });
              this.getData();
          }).catch(() => {});
      },
      handleChangeManualStatus({ $index, row }) {
          const tipsString = row.manual_status === 1 ? this.$t('method.manual_status.unlock') : this.$t('method.manual_status.lock');
          this.$confirm(this.$t('method.manual_status.confirm', { status: tipsString }), this.$t('method.manual_status.title'), {
              type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel')
          }).then(async() => {
              var data = {
                  id: row.id,
                  manual_status: Math.abs(row.manual_status - 1)
              };
              try {
                  row.manual_status === 1 ? await updatePaymentUnlock(data) : await updatePaymentLock(data);
                  // await updatePayment(data);
              } catch (err) {
                  return;
              }
              this.$message({
                  type: 'success',
                  message: this.$t('method.manual_status.success', { status: tipsString })
              });
              this.getData();
          }).catch(() => {});
      },
      checkUPI(upi) {
          this.dialogVisible = true;
          setTimeout(() => {
              this.$refs.qrCodeUrl.innerHTML = '';
              new QRCode(this.$refs.qrCodeUrl, {
                  text: 'upi://pay?pa=' + upi,
                  width: 300,
                  height: 300,
                  colorDark: '#000000',
                  colorLight: '#ffffff',
                  correctLevel: QRCode.CorrectLevel.H
              });
          }, 0);
      },
      /* 编辑 payment */
      handleEdit(scope) {
        this._getChannel(scope);
        this.dialogVisibleEdit = true;
        this.payment.id = scope.row.id;  // Data for id
        this.selectedBankType = parseInt(scope.row.bank_type, 0);  // Data for 银行类型  scope.row.bank_type
        this.selectedAccountType = scope.row.account_type; // Data for 账户类型
        this.partner_id = scope.row.partner_id;  // Data for 所属码商
        this.channel = scope.row.channel;  // Data for 通道号
        this.ifsc = scope.row.ifsc;  // Data for IFSC
        this.upi = scope.row.upi;  // Data for UPI
        this.net_id = scope.row.net_id;  // Data for 网银登录ID
        this.net_trade_pw = scope.row.net_trade_pw;  // Data for 网银交易密码
        this.account = scope.row.account;  // Data for 账户
        this.name = scope.row.name;  // Data for 姓名
        this.net_pw = scope.row.net_pw;  // Data for 网银登录密码
        this.phone = scope.row.phone;  // Data for 注册手机
        this.gmail = scope.row.gmail;  // Data for 谷歌邮箱
        this.gmail_pw = scope.row.gmail_pw;  // Data for 邮箱密码

      },
      /* 新增payment*/
      handleAdd() {
        this._getChannel()
        this.dialogVisibleAdd = true
      },
      /* 确认编辑 */
      async confirmEdit() {
          var data = {
            ...this.payment,
            id: this.payment.id,  // Data for 银行类型
            selectedBankType: this.selectedBankType,  // Data for 银行类型
            selectedAccountType: this.selectedAccountType, // Data for 账户类型
            partner_id: this.partner_id,  // Data for 所属码商
            channel: this.channel.join(','),  // Data for 通道号
            ifsc: this.ifsc,  // Data for IFSC
            upi: this.upi,  // Data for UPI
            net_id: this.net_id,  // Data for 网银登录ID
            net_trade_pw: this.net_trade_pw,  // Data for 网银交易密码
            account: this.account,  // Data for 账户
            name: this.name,  // Data for 姓名
            net_pw: this.net_pw,  // Data for 网银登录密码
            phone: this.phone,  // Data for 注册手机
            gmail: this.gmail,  // Data for 谷歌邮箱
            gmail_pw: this.gmail_pw  // Data for 邮箱密码
          };

          try {
              await updatePaymentEdit(data);
          } catch (err) {
              return;
          }
          this.dialogVisibleEdit = false;
          this.$notify({
              title: this.$t('method.edit.save_success_title'),
              dangerouslyUseHTMLString: true,
              message: this.$t('method.edit.save_success_message'),
              type: 'success'
          });
          this.getData();
      },
      isValidEmail(email) {
        // 简单的邮箱验证正则表达式
        const emailPattern = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        return emailPattern.test(email);
      },
      /* 确认添加*/
      async confirmAdd() {
        // 创建一个空的对象 data
        var data = {};
        // 将 Vue 组件中的每个变量赋值到 data 对象中
        data.selectedBankType = this.selectedBankType;
        data.selectedAccountType = this.selectedAccountType;
        data.ifsc = this.ifsc;
        data.account = this.account;
        data.name = this.name;
        data.net_id = this.net_id;
        data.net_pw = this.net_pw;
        data.net_trade_pw = this.net_trade_pw;
        data.phone = this.phone;
        data.gmail = this.gmail;
        data.gmail_pw = this.gmail_pw;
        data.partner_id = this.partner_id;
        data.upi = this.upi;
        data.channel = this.channel.join(',');

        try {
            await addPayment(data)
        } catch (err) {
            return
        }
        this.dialogVisibleAdd = false
        this.$notify({
            title: this.$t('method.edit.save_success_title'),
            dangerouslyUseHTMLString: true,
            message: this.$t('method.edit.save_success_message'),
            type: 'success'
        })
        this.getData()
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
      // 批量禁用
      async batchDisable() {
          this.bank_type_id = this.$refs.search.formInline.bank_type;
          if (this.bank_type_id === '') {
              this.$message({
                  type: 'error',
                  message: this.$t('method.batch_disable.error')
              });
              return;
          }
          try {
              await batchDisablePayment({
                  'id': this.bank_type_id
              });
          } catch (err) {
              return;
          }
          this.$message({
              type: 'success',
              message: this.$t('method.batch_disable.success')
          });
          this.getData();
      }
  }
  }
  </script>
