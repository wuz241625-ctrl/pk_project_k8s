<template>
    <div class="app-container">
        <baseSearch ref="search" :form-item-list="formItemList" :isdisable="2" @search="getData" />
        <el-table
            :data="smsList"
            style="width: 100%;margin-top:30px;"
            border
            stripe
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
            @sort-change="sort_change"
        >
            <el-table-column align="center" :label="$t('method.Dxlb.form.id')">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.frm')">
                <template slot-scope="scope">
                    {{ scope.row.frm }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.content')">
                <template slot-scope="scope">
                    {{ scope.row.content }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.payment_id')">
                <template slot-scope="scope">
                    {{ scope.row.payment_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.status')">
                <template slot-scope="scope">
<!--                    {{ scope.row.status }}-->
                    <el-tag :type="scope.row.status === 1 ? 'success' : 'danger'">
                    {{ scope.row.status === 1 ? $t('method.Dxlb.statusOptions.1') : $t('method.Dxlb.statusOptions.0') }}
                  </el-tag>
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.remark')">
                <template slot-scope="scope">
                    {{ scope.row.remark }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.received_time')">
                <template slot-scope="scope">
                    {{ scope.row.received_time }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.Dxlb.form.created')">
                <template slot-scope="scope">
                    {{ scope.row.created }}
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
import {getSms} from '@/api/partner'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Dxlb',
    data() {
        return {
            smsList: [],
            order_field: 'count',
            sort: 'desc',
            formItemList: [
                {
                label: this.$t('method.Dxlb.form.payment_id'),
                type: 'input',
                param: 'payment_id'
                },
                {
                label: this.$t('method.Dxlb.form.created'),
                type: 'dateTimePicker',
                pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                param: 'created'
                },
                {
                label: this.$t('method.Dxlb.form.frm'),
                type: 'input',
                param: 'frm'
                },
                {
                label: this.$t('method.Dxlb.form.status'),
                type: 'select',
                param: 'status',
                selectOptions: [
                    {
                      value: 0,
                      label: this.$t('method.Dxlb.statusOptions.0')
                    },
                    {
                      value: 1,
                      label: this.$t('method.Dxlb.statusOptions.1')
                    }
                  ]
                }
            ],
            columnList: [
                {
                name: this.$t('method.Dxlb.form.id'),
                key: 'id'
                },
                {
                name: this.$t('method.Dxlb.form.frm'),
                key: 'frm'
                },
                {
                name: this.$t('method.Dxlb.form.content'),
                key: 'content'
                },
                {
                name: this.$t('method.Dxlb.form.payment_id'),
                key: 'payment_id'
                },
                {
                name: this.$t('method.Dxlb.form.status'),
                key: 'status'
                },
                {
                name: this.$t('method.Dxlb.form.remark'),
                key: 'remark'
                },
                {
                name: this.$t('method.Dxlb.form.created'),
                key: 'created'
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
            if (!data.serchData.created) {
                data.serchData.created = [new Date().toLocaleDateString().split('/').join('-') + ' 00:00:00', new Date().toLocaleString().split('/').join('-')]
            }
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            data.order_field = this.order_field
            data.sort = this.sort
            const res = await getSms(data)
            this.smsList = res.data
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

