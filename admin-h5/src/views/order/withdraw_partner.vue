<template>
    <div class="app-container">
      <baseSearch ref="search" :form-item-list="formItemList" :export-data="exportData" @search="getData"
          @export="getData" />
      <el-form>
          <el-button type="success" plain
              @click="handlecopy(count.successOrder)">{{$t('Mstxdd.buttons.success') }}: {{ count.successOrder }}</el-button>
          <el-button type="danger" plain @click="handlecopy(count.failOrder)">{{$t('Mstxdd.buttons.fail') }}: {{ count.failOrder }}</el-button>
          <el-button type="primary" plain @click="handlecopy(getRate())">{{$t('Mstxdd.buttons.rate') }}: {{ getRate() }}</el-button>
          <el-button type="warning" plain @click="handlecopy(count.processing)">{{$t('Mstxdd.buttons.processing') }}: {{ count.processing }}</el-button>
          <el-button type="warning" plain
              @click="handlecopy(count.processing_amount)">{{$t('Mstxdd.buttons.processingAmount') }}: {{ count.processing_amount }}</el-button>
          <el-button type="primary" plain @click="handlecopy(count.amount)">{{$t('Mstxdd.buttons.amount') }}: {{ count.amount }}</el-button>
      </el-form>

    <el-table :data="orderList" stripe style="width: 100%; margin-top: 30px;" border
    :header-cell-style="{ background:'#DCDFE6', color:'#606266' }">
    <el-table-column fixed="left" align="center" :label="$t('Mstxdd.columns.orderId')" width="240">
        <template slot-scope="scope">
            {{ scope.row.code }}
        </template>
    </el-table-column>
    <el-table-column fixed="left" align="center" :label="$t('Mstxdd.columns.partnerId')">
        <template slot-scope="scope">
            {{ scope.row.partner_id }}
        </template>
    </el-table-column>
    <el-table-column fixed="left" align="center" :label="$t('Mstxdd.columns.adminId')">
        <template slot-scope="scope">
            {{ scope.row.admin_id }}
        </template>
    </el-table-column>
    <el-table-column fixed="left" align="center" :label="$t('Mstxdd.columns.amount')">
        <template slot-scope="scope">
            {{ scope.row.amount }}
        </template>
    </el-table-column>
    <el-table-column fixed="left" align="center" :label="$t('Mstxdd.columns.status')">
        <template slot-scope="scope">
            <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
                {{ statusType.find(item => item.id === scope.row.status).name }}
            </el-tag>
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.paymentCodes')">
        <template slot-scope="scope">
            {{ scope.row.payment_codes }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.amountOrder')">
        <template slot-scope="scope">
            {{ scope.row.amount_order }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.amountSuccess')" width="120">
        <template slot-scope="scope">
            {{ scope.row.amount_success }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.paymentFailCodes')">
        <template slot-scope="scope">
                    {{ scope.row.payment_codes }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.account')" width="200px">
        <template slot-scope="scope">
            {{ scope.row.account }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.name')">
        <template slot-scope="scope">
            {{ scope.row.name }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.type')">
        <template slot-scope="scope">
            {{ scope.row.type }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.timeCreate')" width="160">
        <template slot-scope="scope">
            {{ scope.row.time_create }}
        </template>
    </el-table-column>
    <el-table-column align="center" :label="$t('Mstxdd.columns.timeSuccess')" width="160">
        <template slot-scope="scope">
            {{ scope.row.time_success }}
        </template>
    </el-table-column>
    <el-table-column fixed="right" align="center" :label="$t('Mstxdd.columns.operations')" width="220px">
        <template slot-scope="scope">
            <el-button v-if="scope.row.status in [0, 1]" type="warning" size="small"
                @click="handlePass(scope)">{{$t('Mstxdd.buttons.payment') }}</el-button>
            <el-button v-if="scope.row.status===1" type="warning" size="small"
                @click="confirmFinish(scope)">{{$t('Mstxdd.buttons.confirmFinish') }}</el-button>
            <el-button v-if="scope.row.status in [0, 1]" type="danger" size="small"
                @click="handleCancel(scope)">{{$t('Mstxdd.buttons.reject') }}</el-button>
        </template>
    </el-table-column>
</el-table>



    <div class="block" style="margin-top: 20px;">
        <el-pagination background :current-page="paginationData.page" :page-sizes="[10, 20, 50, 100]"
            :page-size="paginationData.size" layout="total, sizes, prev, pager, next, jumper"
            :total="paginationData.total" @size-change="handleSizeChange" @current-change="handleCurrentChange" />
    </div>

    <el-dialog :visible.sync="dialogVisible" :title="$t('Mstxdd.dialogs.payment')">
        <el-form :model="dialogData" label-width="100px">
            <el-form-item :label="$t('Mstxdd.labels.orderCode')">
                {{ dialogData.code }}
            </el-form-item>
            <el-form-item :label="$t('Mstxdd.labels.amount')">
                {{ dialogData.amount }}
            </el-form-item>
                <!-- <el-form-item label="出款方式">
          <el-select v-model="order.payment_type" placeholder="请选择出款方式">
            <el-option
              v-for="paymenttype in paymentType"
              :key="paymenttype.id"
              :label="paymenttype.name"
              :value="paymenttype.id"
            />
          </el-select>
        </el-form-item> -->
                <!-- <el-form-item v-if="order.payment_type>=2" label="充值订单" wi>
          <el-select v-model="r_order" placeholder="请选择充值订单" style="width: 300px;">
            <el-option
              v-for="item in order.payment_type===2?partner_recharge:merchant_recharge"
              :key="item.code"
              :label="item.code+'|'+item.amount"
              :value="item.code"
            />
          </el-select>
        </el-form-item> -->
                <el-form-item label="出款金额" style="max-width: 282px;" required="true">
                    <el-input v-model="amount_order" placeholder="请输入出款金额"
                        oninput="value=value.replace(/[^0-9.]/g,'')" />
            </el-form-item>
        </el-form>
        <div slot="footer" class="dialog-footer">
            <el-button @click="dialogVisible = false">{{$t('Mstxdd.buttons.cancel') }}</el-button>
            <el-button type="primary" @click="confirmPayment">{{$t('Mstxdd.buttons.confirm') }}</el-button>
        </div>
    </el-dialog>
    </div>
</template>

<script>
    import {
        deepClone
    } from '@/utils'
    import {
        getWithdrawPartner,
        handleWithdrawPartner
    } from '@/api/recharge'
    import { getDateTimePickerOptions } from '@/utils/pickerOptions';

    export default {
        name: 'Shtxdd',
        data() {
            return {
                dialogData: [], // 数据表
                orderList: [], // 数据表
                order: '',
                dialogVisible: false,
                amount_order: '',
                r_order: '',
                statusType: [
                    { id: 0, name: this.$t('method.order.status.pending'), type: 'warning' },
                    { id: 1, name: this.$t('method.order.status.processing'), type: 'warning' },
                    { id: 2, name: this.$t('method.order.status.completed'), type: 'success' },
                    { id: -1, name: this.$t('method.order.status.cancelled'), type: 'info' }
                ],
                paymentType: [
                    { id: 0, name: this.$t('method.order.paymentType.system') },
                    { id: 1, name: this.$t('method.order.paymentType.agency') },
                    { id: 2, name: this.$t('method.order.paymentType.merchantCode') },
                    { id: 3, name: this.$t('method.order.paymentType.merchantRecharge') }
                ],
                partner_recharge: [],
                merchant_recharge: [],
                count: {
                    failOrder: 0,
                    successOrder: 0,
                    rate: 0,
                    processing: 0,
                    amount: 0
                },
                formItemList: [ // 搜索栏设置
                    {
                    label: this.$t('method.order.form.orderNumber'),
                    type: 'input',
                    param: 'code'
                    },
                    {
                    label: this.$t('method.order.form.status'),
                    type: 'select',
                    selectOptions: [],
                    param: 'status'
                    },
                    {
                    label: this.$t('method.order.form.partnerId'),
                    type: 'input',
                    param: 'partner_id'
                    },
                    {
                    label: this.$t('method.order.form.adminId'),
                    type: 'input',
                    param: 'admin_id'
                    },
                    {
                    label: this.$t('method.order.form.completionSpeed1'),
                    type: 'select',
                    selectOptions: [
                        { value: 0, label: this.$t('method.order.form.completionSpeed.green') },
                        { value: 1, label: this.$t('method.order.form.completionSpeed.blue') },
                        { value: 2, label: this.$t('method.order.form.completionSpeed.yellow') },
                        { value: -1, label: this.$t('method.order.form.completionSpeed.red') }
                    ],
                    param: 'status'
                    },
                    {
                    label: this.$t('method.order.form.amount'),
                    type: 'input',
                    param: 'amount'
                    },
                    {
                    label: this.$t('method.order.form.orderTime'),
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'time_create'
                    },
                    {
                    label: this.$t('method.order.form.successTime'),
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'time_success'
                    }
                ],
                params: {},
                exportData: { // 导出信息
                    tHeader: this.$t('method.order.export.header'),
                    filterVal: ['code', 'partner_id', 'admin_id', 'amount', 'status', 'payment_type', 'amount_success', 'amount_order', 'orders', 'time_create', 'payment_codes'],
                    list: [],
                    filename: this.$t('method.order.export.filename')
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
                const res = await getWithdrawPartner(data)
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
            /* 计算成功率 */
            getRate() {
                var orders = this.count.failOrder + this.count.successOrder
                if (orders) {
                    return (this.count.successOrder / orders * 100).toFixed(4) + '%'
                }
                return '0%'
            },
             /* 点击复制 */
    handlecopy(amount) {
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
    /* 出款 */
    async handlePass(scope) {
        this.order = deepClone(scope.row)
        this.amount_order = ''
        this.r_order = ''
        this.dialogVisible = SVGComponentTransferFunctionElement
        // var data = { 'serchData': { 'status': 0 }, 'size': 0, 'page': 0 }
        // try { this.merchant_recharge = (await getRechargeMerchant(data)).data } catch (e) { return }
        // try { this.partner_recharge = (await getRechargePartner(data)).data } catch (e) { return }
    },
    /* 确认出款 */
    async confirmPayment(){},//未知原因方法名对不上，为了不报错添加引用方法，后续确认后再做处理
    async confirmPass() {
        var data = {
            'status': 2
        }
        var message = ''
        if (this.order.payment_type === '') {
            message = this.$t('method.please_select_withdrawal_method')
        } else if (!this.amount_order && [0, 1].indexOf(this.order.payment_type) !== -1) {
            message = this.$t('method.please_enter_withdrawal_amount')
        } else if (!this.r_order && [2, 3].indexOf(this.order.payment_type) !== -1) {
            message = this.$t('method.please_select_recharge_order')
        } else if (!this.amount_order) {
            message = this.$t('method.please_enter_withdrawal_amount')
        }
        if (message) {
            this.$message({
                type: 'warning',
                message: message
            })
        } else {
            data.code = this.order.code
            data.payment_type = this.order.payment_type
            data.amount_order = this.amount_order
            data.r_code = this.r_order
            try {
                await handleWithdrawPartner(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.withdrawal_success')
            })
            this.dialogVisible = false
            this.getData()
        }
    },
    /* 确认收款 */
    confirmFinish({ $index, row }) {
        this.$confirm(this.$t('method.confirm_payment_completed'), this.$t('method.prompt'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async () => {
            const data = {
                'code': row.code,
                'status': 2
            }
            try {
                await handleWithdrawPartner(data)
            } catch (e) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.withdrawal_completed')
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
        }).then(async () => {
            const data = {
                'code': row.code,
                'status': -1
            }
            try {
                await handleWithdrawPartner(data)
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
            }
        }
    }
</script>
<style lang="scss" scoped>
    .el-button {
        margin: 3px;
    }
</style>
