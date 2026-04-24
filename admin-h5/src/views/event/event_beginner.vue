<template>
    <div class="app-container">
        <baseSearch ref="search" :form-item-list="formItemList"
                    :export-data="exportData"
                    @search="getData" @export="getData"/>

        <el-table :data="beginnerLogList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('eventBeginner.columns.id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>
            <!-- <el-table-column align="center" :label="$t('eventBeginner.columns.prize_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.prize_id }}
                </template>
            </el-table-column> -->
            <el-table-column align="center" :label="$t('eventBeginner.columns.partner_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.partner_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.top_parent_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.top_parent_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.pid')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.pid }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.is_finished')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.is_finished ? '是' : '否' }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.is_awarded')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.is_awarded ? '是' : '否' }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.prize_amount')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.prize_amount }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.time_awarded')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.time_awarded }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.time_register')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.time_register }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.time_set_trade_hash')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.time_set_trade_hash }}
                </template>
            </el-table-column>
            <!-- <el-table-column align="center" :label="$t('eventBeginner.columns.time_watch_tutorial_videos')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.time_watch_tutorial_videos }}
                </template>
            </el-table-column> -->
            <el-table-column align="center" :label="$t('eventBeginner.columns.time_order_success')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.time_order_success }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('eventBeginner.columns.create_at')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.create_at }}
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
import { getEventBeginnerProcess } from '@/api/event'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    data() {
        return {
            beginnerLogList: [],
            params: {},
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            formItemList: [
                {   
                    label: this.$t('eventBeginner.columns.create_at'),
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'create_at'
                },
                {
                    label: this.$t('eventBeginner.columns.partner_id'),
                    type: 'input',
                    param: 'partner_id'
                },
                {
                    label: this.$t('eventBeginner.columns.is_finished'),
                    type: 'select',
                    param: 'is_finished',
                    selectOptions: [{ label: '是', value: 1 }, { label: '否', value: 0 }]
                }
            ],
            exportData: {
                tHeader: [
                    "主键ID",
                    "活动设置ID",
                    "码商ID",
                    "顶商ID",
                    "上级ID",
                    "任务是否完成",
                    "是否已经发放奖励",
                    "实际奖励额度",
                    "奖励发放时间",
                    "注册并设置安全码时间",
                    "观看新手教程时间",
                    "关联upi时间",
                    "完成第一笔订单时间",
                    "创建时间"
                ],
                filterVal: ['id', 'prize_id', 'partner_id', 'top_parent_id', 'pid', 'is_finished', 'is_awarded', 'prize_amount', 'time_awarded', 'time_register', 'time_watch_tutorial_videos', 'time_set_trade_hash', 'time_order_success', 'create_at'],
                list: [],
                filename: '新手活动记录导出文件'
            },
        }
    },
    created() {
        this.getData()
    },
    methods: {
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
            console.log('data',data);
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            console.log('data1',data);
            var res = await getEventBeginnerProcess(data)
            if (isExport) {
                this.paginationData.total = res.total
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.beginnerLogList = res.data
                this.paginationData.total = res.total
            }
        },
        handleSizeChange(val) {
            this.paginationData.size = val
            this.getData()
        },
        handleCurrentChange(val) {
            this.paginationData.page = val
            this.getData()
        },
    }
}
</script>

<style lang="scss" scoped>
/* 样式 */
</style> 