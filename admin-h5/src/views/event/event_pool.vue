<template>
    <div class="app-container">
        <el-row :gutter="40" class="panel-group">
            <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
                <div class="card-panel" >
                    <div class="card-panel-icon-wrapper icon-people">
                        <svg-icon icon-class="money" class-name="card-panel-icon" />
                    </div>
                    <div class="card-panel-description">
                        <div class="card-panel-text">
                            {{ $t('eventPoolLog.pool_amount') }}
                        </div>
                        <count-to :start-val="0" :end-val="parseFloat(eventPoolAmount)" :duration="600" class="card-panel-num" />
                    </div>
                </div>
            </el-col>
        </el-row>
        <baseSearch ref="search" :form-item-list="formItemList"
                    :export-data="exportData"
                    @search="getData" @export="getData"/>
        <el-button type="primary" @click="handleAdd">{{ $t('eventPoolLog.button.add') }}</el-button>

        <el-table :data="eventPoolLogList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('eventPoolLog.columns.id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventPoolLog.columns.code')" width="200">
                <template slot-scope="scope">
                    {{ scope.row.code }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventPoolLog.columns.record_type')" width="160">
                <template slot-scope="scope">
                    {{ getRecordtype(scope.row.record_type) }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventPoolLog.columns.change_before')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.change_before }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventPoolLog.columns.amount')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.amount }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventPoolLog.columns.change_after')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.change_after }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventPoolLog.columns.user_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.user_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventPoolLog.columns.remark')" width="340">
                <template slot-scope="scope">
                    {{ scope.row.remark }}
                </template>
            </el-table-column>
            <el-table-column align="header-center" :label="$t('eventPoolLog.columns.created_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.created_at }}
                </template>
            </el-table-column>
        </el-table>


        <div class="block" style="margin-top: 20px;">
            <el-pagination background :current-page="paginationData.page" :page-sizes="[10, 20, 50, 100]"
                           :page-size="paginationData.size" layout="total, sizes, prev, pager, next, jumper"
                           :total="paginationData.total" @size-change="handleSizeChange" @current-change="handleCurrentChange"/>
        </div>

        <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('eventPoolLog.button.edit') : $t('eventPoolLog.button.add')" :close-on-click-modal="false">
            <el-form :model="eventPool" label-width="80px" label-position="left">
                <el-form-item :label="$t('eventPoolLog.form.amount')">
                    <el-input
                        type="number"
                        v-model="eventPool.pool_amount"
                        :placeholder="$t('eventPoolLog.form.amount_placeholder')"
                        min="0"
                        step="0.01"
                    />
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="dialogVisible = false">{{ $t('member.form.cancel') }}</el-button>
                <el-button type="danger" @click="confirmAddPoolAmount">{{ $t('member.form.confirm') }}</el-button>
            </div>
        </el-dialog>
    </div>
</template>

<script>
import { addeventrule, addPoolAmount, getPoolAmount, getPoolLogs } from '@/api/event'
import CountTo from 'vue-count-to'
import Editor from '@tinymce/tinymce-vue'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
const defaultPool = {
    pool_amount: 0.0,               // 账变金额
}
const defaultPoolLog = {
    id: null,                 // 奖励ID
    user_id: '',                // 交易用户ID
    user_type: '',            // 交易用户类型  0码商 1商户
    code: null,            // 流水号
    record_type: '',       // 流水类型  1 奖池增加  2 奖励发放
    change_before: 0.0,          // 账变前金额
    amount: 0.0,               // 账变金额
    change_after: 0.0,               // 账变后金额
    remark: '',               // 奖励金额
    created_at: ''            // 创建时间
}

export default {
    components: {
        Editor,
        CountTo
    },
    data() {
        return {
            eventPool: Object.assign({}, defaultPool),
            eventPoolAmount: 0,
            eventPoolLog: Object.assign({}, defaultPoolLog),
            eventPoolLogList: [],
            dialogVisible: false,
            dialogType: 'new',
            order_field: 'id',
            sort: 'desc',
            params: {},
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            formItemList: [
                {
                    label: this.$t('method.df.form.time_create'),
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'created_at'
                }
            ],
            exportData: {
                tHeader: [
                    "记录ID",
                    "流水号",
                    "流水类型",
                    "账变前金额",
                    "账变金额",
                    "账变后金额",
                    "partner ID",
                    "备注",
                    "创建时间"
                ],
                filterVal: ['id', 'code', 'record_type', 'change_before', 'amount','change_after','user_id', 'remark', 'created_at'],
                list: [],
                filename: '奖池变动记录导出文件'
            },
        }
    },
    created() {
        this.getData()
    },
    methods: {
        // 根据 type 返回对应的文本
        getRecordtype(type) {
            switch (type) {
                case 1:
                    return '奖池增加'
                case 2:
                    return '奖励发放'
                default:
                    return '未知'
            }
        },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
                this.paginationData.size = 10
            }
            var data = {
                order_field: this.order_field,
                sort: this.sort,
                searchData: this.params
            }
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            // 查询奖池总额
            var result = await getPoolAmount(data)
            this.eventPoolAmount = result.data.pool_amount

            var res = await getPoolLogs(data)
            if (isExport) {
                this.paginationData.total = res.total
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.eventPoolLogList = res.data

                this.paginationData.total = res.total
            }
        },
        /* 新增成员*/
        handleAdd() {
            this.eventPool = Object.assign({}, defaultPool)
            this.dialogType = 'new'
            this.dialogVisible = true
        },
        async confirmAddPoolAmount() {
            var data = this.eventPool
            //根据类型判断参数是否为空
            if (!data.pool_amount  || data.pool_amount === 0) {
                this.$message({
                    type: 'warning',
                    message: '增加的金额不能为空'
                });
                return;
            }
            try {
                await addPoolAmount(data)
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.submit_success')
            })
            await this.getData()
            this.dialogVisible = false
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
    }
}
</script>
<style lang="scss" scoped>
.show-pwd {
    position: absolute;
    right: 10px;
    font-size: 16px;
    cursor: pointer;
    user-select: none;
}
.panel-group {
    margin-top: 18px;

    .card-panel-col {
        margin-bottom: 32px;
    }

    .card-panel {
        height: 108px;
        cursor: pointer;
        font-size: 12px;
        position: relative;
        overflow: hidden;
        color: #666;
        background: #fff;
        box-shadow: 4px 4px 40px rgba(0, 0, 0, .05);
        border-color: rgba(0, 0, 0, .05);

        &:hover {
            .card-panel-icon-wrapper {
                color: #fff;
            }

            .icon-people {
                background: #40c9c6;
            }

            .icon-message {
                background: #36a3f7;
            }

            .icon-money {
                background: #f4516c;
            }

            .icon-shopping {
                background: #34bfa3
            }
        }

        .icon-people {
            color: #40c9c6;
        }

        .icon-message {
            color: #36a3f7;
        }

        .icon-money {
            color: #f4516c;
        }

        .icon-shopping {
            color: #34bfa3
        }

        .card-panel-icon-wrapper {
            float: left;
            margin: 14px 0 0 14px;
            padding: 16px;
            transition: all 0.38s ease-out;
            border-radius: 6px;
        }

        .card-panel-icon {
            float: left;
            font-size: 48px;
        }

        .card-panel-description {
            float: right;
            font-weight: bold;
            margin: 26px;
            margin-left: 0px;

            .card-panel-text {
                line-height: 18px;
                color: rgba(0, 0, 0, 0.45);
                font-size: 16px;
                margin-bottom: 12px;
            }

            .card-panel-num {
                font-size: 20px;
            }
        }
    }
}

@media (max-width:550px) {
    .card-panel-description {
        display: none;
    }

    .card-panel-icon-wrapper {
        float: none !important;
        width: 100%;
        height: 100%;
        margin: 0 !important;

        .svg-icon {
            display: block;
            margin: 14px auto !important;
            float: none !important;
        }
    }
}
</style>
