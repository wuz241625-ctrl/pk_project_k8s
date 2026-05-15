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
<!--      <el-button type="warning" plain @click="dialogVisible=true">{{ $t('method.ds.orderManagement.buttons.processing') }}{{ count.processing }}</el-button>-->
      <el-button type="warning" plain @click="getProcessing()">{{ $t('method.ds.orderManagement.buttons.processing') }}{{ count.processing }}</el-button>
      <el-button
        type="warning"
        plain
        @click="handleCopy(count.processing_amount)"
      >{{ $t('method.ds.orderManagement.buttons.processingAmount') }} {{ count.processing_amount }}</el-button>
      </el-form>
    <el-table
      :data="orderList"
      style="margin-top:6px;"
      stripe
      border
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      v-horizontal-scroll="'always'"
    >


<!-- 查单时间 -->
<el-table-column fixed="left" align="left" label="查单时间">
  <template slot-scope="scope">
    {{ scope.row.created_at }} <!-- 显示商家ID -->
  </template>
</el-table-column>

      <!-- 商家订单号 -->
<el-table-column fixed="left" align="left" :label="$t('method.ds.orderManagement.table.merchantId')" width="200" show-overflow-tooltip>
  <template slot-scope="scope">
    {{ scope.row.merchant_code }} <!-- 显示商家的订单号 -->
  </template>
</el-table-column>

<!-- 状态 -->
<el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.status')">
  <template slot-scope="scope">
    <el-tag :type="statusType.find(item => item.id === scope.row.cd_status).type">
      {{ statusType.find(item => item.id === scope.row.cd_status).name }} <!-- 显示订单状态 -->
    </el-tag>
  </template>
</el-table-column>


<!-- 商家ID -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.merchantId')">
  <template slot-scope="scope">
    {{ scope.row.merchant_id }} <!-- 显示商家ID -->
  </template>
</el-table-column>

<!-- 备注 -->
<el-table-column align="center" label="备注">
  <template slot-scope="scope">
    {{ displayCdMemo(scope.row.cd_memo) }}
  </template>
</el-table-column>

<!-- 顶商ID -->
<el-table-column align="center" label="顶商ID">
  <template slot-scope="scope">
    {{ scope.row.top_level_partner_id }} <!-- 显示顶商ID -->
  </template>
</el-table-column>

<!-- 顶商名称 -->
<el-table-column align="center" label="顶商名称">
  <template slot-scope="scope">
    {{ scope.row.top_level_partner_id_name }} <!-- 显示顶商名称 -->
  </template>
</el-table-column>

<!-- 订单编号 -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.orderId')" width="200">
  <template slot-scope="scope">
    {{ scope.row.code }} <!-- 显示订单编号 -->
  </template>
</el-table-column>

<!-- 码商 -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.partnerId')">
  <template slot-scope="scope">
    {{ scope.row.partner_id }} <!-- 显示码商 -->
  </template>
</el-table-column>

<!-- 金额 -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.amount')">
  <template slot-scope="scope">
    {{ scope.row.amount }} <!-- 显示订单金额 -->
  </template>
</el-table-column>

<!-- UTR -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.utr')" width="120">
  <template slot-scope="scope">
    {{ scope.row.utr }} <!-- 显示UTR编号 -->
  </template>
</el-table-column>

<!-- UPI -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.upi')"  width="100" show-overflow-tooltip>
  <template slot-scope="scope">
    {{ scope.row.upi }} <!-- 显示UPI编号 -->
  </template>
</el-table-column>

<!-- Bank ID -->
<el-table-column align="center" label="Bank ID" width="120">
  <template slot-scope="scope">
    {{ scope.row.payment_id }} <!-- 显示银行的ID/授权码 -->
  </template>
</el-table-column>

<!-- 接单时间 -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.acceptTime')" width="160">
  <template slot-scope="scope">
    {{ scope.row.time_accept }} <!-- 显示订单的接单时间 -->
  </template>
</el-table-column>

<!-- 支付时间 -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.paymentTime')" width="160">
  <template slot-scope="scope">
    {{ scope.row.time_payed }} <!-- 显示支付时间 -->
  </template>
</el-table-column>

<!-- 查单人ID -->
<el-table-column align="center" label="查单人ID">
  <template slot-scope="scope">
    {{ scope.row.cd_admin_id }} <!-- 显示操作员ID -->
  </template>
</el-table-column>


<!-- 审核人ID -->
<el-table-column align="center" label="审核人ID">
  <template slot-scope="scope">
    {{ scope.row.admin_id }} <!-- 显示操作员ID -->
  </template>
</el-table-column>

<!-- 用户IP -->
<el-table-column align="center" :label="$t('method.ds.orderManagement.table.userIP')">
  <template slot-scope="scope">
    {{ scope.row.player_ip }} <!-- 显示用户IP -->
  </template>
</el-table-column>



      <el-table-column fixed="right" align="center" :label="$t('method.ds.orderManagement.table.operation')" width="120">
        <template slot-scope="scope">
          <!-- 点审核出现上面这个页面
           0/1/2/3   待审核/审核/确认审核/反审核
          审核只有在待审核的时候显示
          点完审核后出现确认审核和反审核
          点击确认审核为完成审核反审核还展示
          点击反审核状态修改为待审核 -->
          <!-- <el-button type="primary" size="small" @click="handleEdit(scope)" style="margin-top:10px;">查单</el-button> -->
          <el-button type="success"
          v-if=" scope.row.cd_status === 0" size="small" @click="review(scope)" style="margin-top:10px; margin-left:10px;">审核</el-button>
          <el-button v-if="scope.row.cd_status === 1" type="warning" size="small" @click="updateCdAudit(scope)" style="margin-top:10px; margin-left:10px;">确认审核</el-button>
          <el-button v-if="scope.row.cd_status === 1 || scope.row.cd_status === 2" type="danger" size="small" @click="updateNoConfirm(scope)" style="margin-top:10px; margin-left:10px;">反审核</el-button>

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

    <el-dialog :visible.sync="dialogVisible" :title="$t('method.ds.orderManagement.dialog.processingOrders')">
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


  <el-dialog :visible.sync="dialogVisibleEdit" title="查单" :close-on-click-modal="false" :style="{ width: '150%', left: '-15%' }">
    <el-form :model="ds" label-width="115px" label-position="left">
      <div class="status-container">
        <p class="status-label">当前状态: <span class="status-value">{{ status }}</span></p>
        <p class="time-label">查单时间: <span class="time-value">{{ queryTime }}</span></p>
      </div>

        <el-form-item label="客户回复状态"  class="form-item">
          <el-select v-model="selectedReplyStatus" placeholder="选择客户回复状态">
            <el-option
              v-for="status in replyStatuses"
              :key="status.value"
              :label="status.label"
              :value="status.value"
            ></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="UTR"  class="form-item">
          <el-input size="small" v-model="utr" placeholder="Please enter utr" width="100" :style="{ width: '300px' }"/>
        </el-form-item>

    </el-form>

    <div style="text-align:right;">
      <el-button type="primary" @click="dialogVisibleEdit=false">{{ $t('method.Mslb.buttons.cancel') }}</el-button>
      <el-button type="danger" @click="updateCdConfirm">{{ $t('method.Mslb.buttons.confirm') }}</el-button>
    </div>
  </el-dialog>

  </div>
</template>

<script>
import {
    getorderdscd,
    handleOrder,
    handleNotifyds,
    updateCdAudit,
    updateCdConfirm,
    updateNoConfirm,
    getCdType,
    getDSCDProcessing
} from '@/api/order'
import {
    deepClone
} from '@/utils'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Dsddcd',
    data() {
        return {
            urlEdit: false,
            zhArray: {},
            enArray: {},
            utr: '',
            status: '待处理',
            currentLanguage: this.$i18n.locale,
            selectedOperation: "审核", // 默认选择“审核”
            selectedReplyStatus: '',
            replyStatuses: [], // 用于存储从接口获取的状态数据
            queryTime: '',
            code: '',
            dialogVisibleEdit: false,
            processing_: false,
            ds: {},
            count: {
                failOrder: 0,
                successOrder: 0,
                rate: 0,
                processing: 0,
                amount: 0,
                realpay: 0,
                earn_merchant: 0,
                earn_partner: 0,
                earn_system: 0
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
        label: '查单时间',
        type: 'dateTimePicker',
        pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
        param: 'created_at'
    },

    {
        label: '查单人ID',
        type: 'input',
        param: 'cd_admin_id'
    },
    {
        label: '审核人ID',
        type: 'input',
        param: 'admin_id'
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
        param: 'cd_status'
    },
    {
        label: this.$t('method.ds.form.time_create'),
        type: 'dateTimePicker',
        pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
        param: 'time_create'
    },
    {
        label: this.$t('method.ds.form.time_success'),
        type: 'dateTimePicker',
        pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
        param: 'time_success'
    },
    {
        label: this.$t('method.ds.form.top_partner_id'),
        type: 'input',
        param: 'top_partner_id'
    }
],
statusType: [
    {
        id: 0,
        name: '待审核',
        type: 'warning'
    },
    {
        id: 1,
        name: '审核',
        type: 'danger'
    },
    {
        id: 2,
        name: '确定审核',
        type: 'success'
    },
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
        this.$t('method.ds.export.player_ip')
    ],
    filterVal: [
        'code', 'merchant_code', 'channel_code', 'amount', 'status', 'merchant_id', 'auth_code',
        'utr', 'partner_id', 'payment_id', 'time_create', 'time_accept', 'time_payed', 'time_success',
        'realpay', 'merchant_rate', 'poundage', 'earn_merchant', 'earn_partner', 'earn_system', 'player_ip'
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
            // 处理中的商户订单量
            merchant_processings: []
        }
    },
    computed: {
        displayCdMemo() {
          return (cdMemo) => {
            return this.locale === 'en'
              ? this.enArray[cdMemo] || cdMemo
              : this.zhArray[cdMemo] || cdMemo;
          };
        }
    },
    created() {
        this.code = this.$route.params.code
        this.fetchReplyStatuses()
        this.statusType.forEach(statusType => {
                this.formItemList.find(item => item.type === 'select').selectOptions.push({
                    value: statusType.id,
                    label: statusType.name
                })
            })
        this.getData()
    },
    methods: {
        addUtr(scrow) {
          this.code = scrow.row.code
          this.urlEdit = true;
        },
        getMemo(cdMemo) {
          const locale = this.$i18n.locale; // 获取当前语言环境

          if (locale === 'en') {
            // 中文环境
            return this.enArray[cdMemo] || cdMemo; // 如果找到对应的英文，返回英文，否则返回 cdMemo
          } else if (locale === 'zh') {
            // 英文环境
            return this.zhArray[cdMemo] || cdMemo; // 如果找到对应的中文，返回中文，否则返回 cdMemo
          }
          return cdMemo; // 默认返回 cdMemo
        },
        getMemoCh(cdMemo) {
          const status = this.replyStatuses.find(item => item.value === cdMemo);
          return status ? status.label : cdMemo; // Return label if found, else return cdMemo
        },
        async review(scope) {
          // console.log('执行审核操作');
          this.dialogVisibleEdit = true
          this.code = scope.row.code
            var msg = ''
            // 0/1/2/3  待查询/审核/确认审核/反审核
            switch(scope.row.cd_status) {
                case 0:
                case 3:
                  msg = '待查询'
                  break;
                case 1:
                  msg = '审核'
                  break;
                case 2:
                  msg = '确认审核'
                  break;
            }
            const status = msg;
            this.selectedReplyStatus = this.getMemo(scope.row.cd_memo)
            // const queryTime = new Date().toLocaleString(); // 获取当前时间
            const merchant_order = scope.row.code; // 假设这是你要传递的 code 值
            // 设置状态和查询时间
            this.status = status;
            this.queryTime = scope.row.created_at;
            this.merchant_order = merchant_order;
            this.utr = scope.row.utr
            await this.fetchReplyStatuses(scope)
        },
        async updateCdConfirm() {
          try {

            // 获取当前语言环境
            const locale = this.$i18n.locale;
            // 根据当前语言环境决定 cd_memo 的值
            const cdMemo = locale === 'en'
            ? this.replyStatuses.find(item => item.value === this.selectedReplyStatus)?.label // 英文环境取 label
            : this.getMemo(this.selectedReplyStatus); // 中文环境取 getMemo 处理后的值
            // 调用 API 更新确认审核状态
            await updateCdConfirm({
              code: this.code,
              cd_memo: cdMemo,
              cd_status: 1,
              utr: this.utr
            });

            // 成功提示
            this.$message({
              type: 'success',
              message: '确认审核处理成功'
            });

            // 刷新数据
            this.getData();
            this.dialogVisibleEdit = false;

          } catch (err) {
            // 错误提示
            // this.$message({
            //   type: 'error',
            //   message: '确认审核处理失败，请重试'
            // });
            // console.error('确认审核处理失败:', err);
          }
        },

        async updateCdAudit(scope) {
          // console.log('执行审核操作');
          try {
            // 调用 API 更新审核状态
            await updateCdAudit({
              code: scope.row.code,
              cd_memo: scope.row.cd_memo ,
              cd_status: 2,
              utr: scope.row.utr
            });

            // 成功提示
            this.$message({
              type: 'success',
              message: '审核处理成功'
            });

            // 刷新数据
            this.getData();
            this.dialogVisibleEdit = false;

          } catch (err) {
            // 错误提示
            // this.$message({
            //   type: 'error',
            //   message: '审核处理失败，请重试'
            // });
            // console.error('审核处理失败:', err);
          }

        },

        async updateNoConfirm(scope) {
          // console.log('执行反审核操作');
          try {
            // 调用 API 更新反审核状态
            await updateNoConfirm({
              code: scope.row.code,
              cd_memo: scope.row.cd_memo ,
              cd_status: 0,
              utr: scope.row.utr
            });

            // 成功提示
            this.$message({
              type: 'success',
              message: '反审核处理成功'
            });

            // 刷新数据
            this.getData();
            this.dialogVisibleEdit = false;

          } catch (err) {
            // 错误提示
            // this.$message({
            //   type: 'error',
            //   message: '反审核处理失败，请重试'
            // });
            // console.error('反审核处理失败:', err);
          }


        },
        async fetchReplyStatuses(scope = '') {
          try {
            const { data } = await getCdType(scope); // 使用解构赋值获取 data

            // 使用条件运算符设置 replyStatuses
            this.replyStatuses = Array.isArray(data)
              ? data.map(item => ({
                  // 根据当前语言环境设置 label 和 value
                  label: this.$i18n.locale === 'en' ? item.description || '' : item.name || '未知', // 英文环境取 description，中文环境取 name
                  value: this.$i18n.locale === 'en' ? item.name || '未知' : item.description || '', // 英文环境取 name，中文环境取 description
                }))
              : []; // 如果数据格式不正确，则设为空数组


              // 生成两个数组
            this.zhArray = {};
            this.enArray = {};

            this.replyStatuses.forEach(item => {
              // 中文环境映射：英文 -> 中文
              this.zhArray[item.value] = item.label;
              // 英文环境映射：中文 -> 英文
              this.enArray[item.label] = item.value;
            });


          } catch (error) {
            // console.error('获取客户回复状态失败:', error);
            this.replyStatuses = []; // 发生错误时清空回复状态
          }
        },
        /* 编辑码商*/
        async handleEdit(scope) {
            this.dialogVisibleEdit = true
            this.ds = deepClone(scope.row)
            var msg = ''
            // 0/1/2/3  待查询/审核/确认审核/反审核
            switch(scope.row.cd_status) {
                case 0:
                case 3:
                  msg = '待查询'
                  break;
                case 1:
                  msg = '审核'
                  break;
                case 2:
                  msg = '确认审核'
                  break;
            }
            const status = msg;
            // this.selectedReplyStatus = scope.row.cd_memo
            this.selectedReplyStatus = this.getMemo(scope.row.cd_memo);

            const queryTime = new Date().toLocaleString(); // 获取当前时间
            const merchant_order = scope.row.code; // 假设这是你要传递的 code 值
            // 设置状态和查询时间
            this.status = status;
            this.queryTime = queryTime;
            this.merchant_order = merchant_order;
            await this.fetchReplyStatuses(scope)

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
            if(this.processing_){
                this.processing_ = false;
                const res = await getDSCDProcessing(data)
                if (isExport) {
                    this.exportData.list = res.data
                    this.$refs.search.exportExcel()
                } else {
                    this.merchant_processings = res.merchant_processing?.map(item => ({
                            ...item,
                            total: +(item.total || 0)
                        })) || []
                }
            }else {
                const res = await getorderdscd(data)
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
                  this.paginationData.total = res.total
                }
            }
        },
        getProcessing(){
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
    handleOrder(scope) {
        this.$prompt(this.$t('method.enter_trx'), this.$t('method.supplement_order'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            inputPattern: /\S+/,
            inputErrorMessage: this.$t('method.enter_trx'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async({
            value
        }) => {
            try {
                await handleOrder({
                    'code': scope.row.code,
                    'trans_id': value.trim()
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
<style scoped>
.data-table {
  margin: 20px;
}
.status-container {
  background-color: #ffffff; /* 背景颜色 */
  padding: 15px 25px; /* 内边距 */
  border-radius: 8px; /* 圆角 */
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); /* 阴影效果 */
  margin-bottom: 20px; /* 底部外边距，分隔其他内容 */
  border-left: 5px solid #007bff; /* 左侧边框强调 */
}

.status-label,
.time-label {
  font-size: 16px; /* 字体大小 */
  color: #333; /* 字体颜色 */
  margin: 0; /* 去除默认外边距 */
  font-family: 'Arial', sans-serif; /* 字体 */
}

.status-value,
.time-value {
  font-weight: bold; /* 加粗 */
  color: #007bff; /* 强调颜色 */
}

.status-label:hover,
.time-label:hover {
  text-decoration: underline; /* 鼠标悬停下划线 */
}

.status-container p {
  line-height: 1.5; /* 行高 */
}

</style>
