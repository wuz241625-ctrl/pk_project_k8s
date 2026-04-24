<template>
    <div class="app-container">
        <baseSearch ref="search" :form-item-list="formItemList" :export-data="exportData" @search="getData"
            @export="getData" />
        <el-button type="primary" @click="handleAdd">{{ $t('withdraw.dialog.title') }}</el-button>
        <el-table :data="orderList" stripe style="width: 100%;margin-top:30px;" border
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column fixed="left" align="center" :label="$t('withdraw.table.orderNumber')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.code }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('withdraw.table.orderAmount')">
                <template slot-scope="scope">
                    {{ scope.row.amount }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('withdraw.table.status')">
                <template slot-scope="scope">
                    <el-tag :type="statusType.find(item => item.id === scope.row.status).type">
                        {{ $t(`withdraw.status.${statusType.find(item => item.id === scope.row.status).name}`) }}
                    </el-tag>
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('withdraw.table.usdtAddress')" width="400">
                <template slot-scope="scope">
                    {{ scope.row.address }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('withdraw.table.orderTime')">
                <template slot-scope="scope">
                    {{ scope.row.time_create }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('withdraw.table.successTime')">
                <template slot-scope="scope">
                    {{ scope.row.time_success }}
                </template>
            </el-table-column>
            <el-table-column fixed="right" align="center" :label="$t('withdraw.table.operation')">
                <template slot-scope="scope">
                    <el-button type="primary" size="small" @click="handleCopy(scope.row.address)">
                        {{ $t('withdraw.table.copyAddress') }}
                    </el-button>
                </template>
            </el-table-column>
        </el-table>

        <!-- Withdraw Dialog -->
        <el-dialog :visible.sync="dialogVisible" :title="$t('withdraw.dialog.title')" :close-on-click-modal="false">
            <el-form :model="withdraw" label-width="180px" label-position="left">
                <el-form-item :label="$t('withdraw.dialog.amount')">
                    <el-input v-model="withdraw.amount" :placeholder="$t('withdraw.dialog.placeholderAmount')" style="max-width: 400px;" />
                </el-form-item>
                <el-form-item :label="$t('withdraw.dialog.address')">
                    <el-input v-model="withdraw.address" :placeholder="$t('withdraw.dialog.placeholderAddress')" style="max-width: 400px;" />
                </el-form-item>
                <el-form-item :label="$t('withdraw.dialog.googleKey')">
                    <el-input v-model="withdraw.google" :placeholder="$t('withdraw.dialog.placeholderGoogle')" style="max-width: 400px;" maxlength="6" />
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="dialogVisible=false">{{ $t('withdraw.dialog.cancel') }}</el-button>
                <el-button type="danger" @click="confirmWithdraw">{{ $t('withdraw.dialog.confirm') }}</el-button>
            </div>
        </el-dialog>

        <!-- Pagination -->
        <div class="block" style="margin-top: 20px;">
            <el-pagination background :current-page="paginationData.page" :page-sizes="[10, 20, 50, 100]"
                :page-size="paginationData.size" :total="paginationData.total"
                layout="total, sizes, prev, pager, next, jumper"
                @size-change="handleSizeChange" @current-change="handleCurrentChange" />
        </div>
    </div>
</template>

<script>
    import {
        getWithdraw,
        addWithdraw
    } from '@/api/order'
    import { getDateTimePickerOptions } from '@/utils/pickerOptions';

    export default {
        data() {
            return {
                params: {},
                orderList: [], // 数据表
                dialogVisible: false,
                statusType: [{
                        'id': 0,
                        'name': 'pending',
                        'type': 'warning'
                    },
                    {
                        'id': 1,
                        'name': 'processing',
                        'type': 'danger'
                    },
                    {
                        'id': 2,
                        'name': 'completed',
                        'type': 'success'
                    },
                    {
                        'id': -1,
                        'name': 'cancelled',
                        'type': 'info'
                    }
                ],
                withdraw: {},
                formItemList: [
                {
                    labelKey: 'withdraw.search.code',
                    type: 'input',
                    param: 'code'
                },
                {
                    labelKey: 'withdraw.search.status',
                    type: 'select',
                    selectOptions: [],
                    param: 'status'
                },
                {
                    labelKey: 'withdraw.search.amount',
                    type: 'input',
                    param: 'amount'
                },
                {
                    labelKey: 'withdraw.search.time_create',
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'time_create'
                },
                {
                    labelKey: 'withdraw.search.time_success',
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'time_success'
                }
                ],
                exportData: { // 导出信息
                    tHeader: [
                        this.$t('withdraw.exportData.tHeader.order_number'),
                        this.$t('withdraw.exportData.tHeader.order_amount'),
                        this.$t('withdraw.exportData.tHeader.status'),
                        this.$t('withdraw.exportData.tHeader.usdt_address'),
                        this.$t('withdraw.exportData.tHeader.order_time'),
                        this.$t('withdraw.exportData.tHeader.completion_time')
                    ],
                    filterVal: ['code', 'amount', 'status', 'address', 'amount_success', 'time_create'],
                    list: [],
                    filename: this.$t('withdraw.exportData.filename')
                },
                paginationData: { // 翻页信息
                    page: 1,
                    size: 10,
                    total: 0
                }
            }
        },
        created() {
            this.statusType.forEach(statusType => {
                this.formItemList.find(item => item.type === 'select').selectOptions.push({
                    value: statusType.id,
                    label: this.$t(`withdraw.status.${statusType.name}`)
                })
            })
            this.getData()
        },
        methods: {
            /* 获取数据*/
            async getData(params = {}, isExport = false) {
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
                const res = await getWithdraw(data)
                if (isExport) {
                    this.exportData.list = res.data
                    this.$refs.search.exportExcel()
                } else {
                    this.orderList = res.data
                    this.count = res.count
                    this.paginationData.total = res.total
                }
            },
            /* 点击复制 */
            handleCopy(address) {
                const oInput = document.createElement('input')
                oInput.value = address
                document.body.appendChild(oInput)
                oInput.select() // 选择对象;
                document.execCommand('Copy') // 执行浏览器复制命令
                this.$notify({
                    title: this.$t('withdraw.messages.copySuccess'),
                    type: 'success'
                })
            },
            /* 提现*/
            handleAdd() {
                this.dialogVisible = true
                this.withdraw = {}
            },
            async confirmWithdraw() {
                var number = /^[\d]*$/
                if (!number.test(this.withdraw.amount) || this.withdraw.amount <= 0 || !number.test(this.withdraw
                        .google)) {
                    this.$message({
                        type: 'warning',
                        message: this.$t('withdraw.messages.inputError')
                    })
                } else {
                    try {
                        await addWithdraw(this.withdraw)
                    } catch (err) {
                        return
                    }
                    this.$message({
                        type: 'success',
                        message: this.$t('withdraw.messages.withdrawSubmitted')
                    })
                    this.dialogVisible = false
                    this.getData()
                }
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
