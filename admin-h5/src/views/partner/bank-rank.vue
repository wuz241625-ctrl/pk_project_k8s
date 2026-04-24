<template>
    <div class="app-container">
        <baseSearch ref="search" :form-item-list="formItemList" :isdisable="10" @search="getData" />
        <el-table
            :data="merchantList"
            style="width: 100%;margin-top:30px;"
            border
            stripe
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
            @sort-change="sort_change"
        >
            <el-table-column align="center" :label="$t('Yhpm.form.bankName')">
                <template slot-scope="scope">
                    {{ scope.row.name }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('Yhpm.form.orderCount')" sortable>
                <template slot-scope="scope">
                    {{ scope.row.count }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('Yhpm.form.orderAmount')" sortable>
                <template slot-scope="scope">
                    {{ scope.row.amount }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('Yhpm.form.successOrderCount')" sortable>
                <template slot-scope="scope">
                    {{ scope.row.success_count }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('Yhpm.form.successAmount')" sortable>
                <template slot-scope="scope">
                    {{ scope.row.success_amount }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('Yhpm.form.successRate')" sortable>
                <template slot-scope="scope">
                    {{ scope.row.rate + '%' }}
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
    </div>
</template>

<script>
import { getBankRank } from '@/api/partner'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Yhpm',
    data() {
        return {
            merchantList: [],
            order_field: 'count',
            sort: 'desc',
            formItemList: [
                {
                label: this.$t('Yhpm.ds.form.channel_code'),
                type: 'input',
                param: 'channel_code'
                },
                {
                label: this.$t('Yhpm.ds.form.time_create'),
                type: 'dateTimePicker',
                pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                param: 'time_create'
                }
            ],
            columnList: [
                {
                name: this.$t('Yhpm.ds.column.order_count'),
                key: 'count'
                },
                {
                name: this.$t('Yhpm.ds.column.order_amount'),
                key: 'amount'
                },
                {
                name: this.$t('Yhpm.ds.column.success_order_count'),
                key: 'success_count'
                },
                {
                name: this.$t('Yhpm.ds.column.success_amount'),
                key: 'success_amount'
                },
                {
                name: this.$t('Yhpm.ds.column.success_rate'),
                key: 'rate'
                }
            ],
            params: {},
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
        async getData(params) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            var data = {}
            data.serchData = this.params
            if (!data.serchData.time_create) {
                data.serchData.time_create = [new Date().toLocaleDateString().split('/').join('-') + ' 00:00:00', new Date().toLocaleString().split('/').join('-')]
            }
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            data.order_field = this.order_field
            data.sort = this.sort
            const res = await getBankRank(data)
            this.merchantList = res.data
            this.paginationData.total = res.total
        },
        /* 排序*/
        async sort_change({ column }) {
            this.order_field = this.columnList.find(item => item.name === column.label).key
            if (column.order === 'ascending') {
                this.sort = 'asc'
            } else if (column.order === 'descending') {
                this.sort = 'desc'
            } else {
                this.sort = null
            }
            this.getData()
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

