<template>
    <div class="app-container">

        <baseSearch ref="search" :form-item-list="formItemList"
                    :export-data="exportData"
                    @search="getData" @export="getData"/>

        <el-table :data="eventLogList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('eventLog.columns.id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventLog.columns.user_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.user_id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventLog.columns.prize_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.prize_id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventLog.columns.prize_title')" width="340">
                <template slot-scope="scope">
                    {{ scope.row.prize_title }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventLog.columns.money')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.money }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventLog.columns.remark')" width="340">
                <template slot-scope="scope">
                    {{ scope.row.remark }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('eventLog.columns.created_at')" width="240">
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
    </div>
</template>

<script>
import {geteventlogs} from '@/api/eventrule'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
const defaultEvent = {
    id: null,                 // 奖励ID
    user_id: '',                // 奖励标题
    user_name: '',            // 用户名
    prize_id: null,            // 活动ID
    prize_detail_id: '',       // 活动详情ID
    prize_title: '',          // 活动标题
    money: 0.0,               // 奖励金额
    remark: '',               // 奖励金额
    created_at: ''            // 创建时间
}

export default {
    data() {
        return {
            event: Object.assign({}, defaultEvent),
            eventLogList: [],
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
                    label: this.$t('eventLog.columns.prize_id'),
                    type: 'input',
                    param: 'prize_id'
                },
                {
                    label: this.$t('eventLog.columns.user_id'),
                    type: 'input',
                    param: 'user_id'
                },
                {
                    label: this.$t('method.df.form.time_create'),
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'created_at'
                },
                {
                    label: '标题',
                    // label: this.$t('method.df.form.time_create'),
                    type: 'input',
                    param: 'prize_title'
                },
            ],
            exportData: {
                tHeader: [
                    "奖励记录ID",
                    "partner ID",
                    "活动ID",
                    "活动标题",
                    "奖励金额",
                    "备注",
                    "创建时间"
                ],
                filterVal: ['id', 'user_id', 'prize_id', 'prize_title', 'money', 'remark', 'created_at'],
                list: [],
                filename: '奖励记录导出文件'
            },
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
            // data.size = this.paginationData.size
            // data.page = this.paginationData.page

            var res = await geteventlogs(data)
            if (isExport) {
                this.paginationData.total = res.total
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.eventLogList = res.data

                this.paginationData.total = res.total
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
</style>
