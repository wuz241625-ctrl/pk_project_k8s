<template>
    <div class="app-container">
        <baseSearch ref="search" :form-item-list="formItemList" @search="getData" @export="getData"/>
        <el-button type="primary" @click="handleAddChance">{{ $t('eventChance.button.add') }}</el-button>

        <el-table :data="chanceList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('eventChance.columns.id')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventChance.columns.user_id')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.user_id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventChance.columns.chance_num')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.chance_num }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventChance.columns.created_at')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.created_at }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventChance.columns.updated_at')" width="240">
                <template slot-scope="scope">
                    {{ scope.row.updated_at }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventChance.columns.operation')" width="320">
                <template slot-scope="scope">
                    <el-button type="primary" size="small" @click="handleViewLog(scope)">
                        {{ $t('eventChance.button.viewLog') }}
                    </el-button>
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

        <!-- 添加抽奖机会弹窗 -->
        <el-dialog
            :visible.sync="addDialogVisible"
            :title="$t('eventChance.dialog.addTitle')"
            :close-on-click-modal="false"
        >
            <el-form :model="chanceForm" label-width="120px" label-position="left">
                <el-form-item :label="$t('eventChance.form.user_id')" required>
                    <el-input v-model="chanceForm.user_id" type="number" :placeholder="$t('eventChance.form.user_id_placeholder')"/>
                </el-form-item>
                <el-form-item :label="$t('eventChance.form.add_num')" required>
                    <el-input v-model="chanceForm.num" type="number" :placeholder="$t('eventChance.form.add_num_placeholder')"/>
                </el-form-item>
                <el-form-item :label="$t('eventChance.form.remark')">
                    <el-input
                        v-model="chanceForm.remark"
                        type="textarea"
                        :placeholder="$t('eventChance.form.remark_placeholder')"
                    />
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button @click="addDialogVisible = false">{{ $t('eventChance.button.cancel') }}</el-button>
                <el-button type="primary" @click="confirmAddChance">{{ $t('eventChance.button.confirm') }}</el-button>
            </div>
        </el-dialog>

        <!-- 查看变动记录弹窗 -->
        <el-dialog
            :visible.sync="logDialogVisible"
            :title="$t('eventChance.dialog.logTitle')"
            width="70%"
        >
            <el-table :data="logList" border stripe>
                <el-table-column align="center" :label="$t('eventChance.columns.log_id')" width="80" prop="id"/>
                <el-table-column align="center" :label="$t('eventChance.columns.prize_id')" width="100" prop="prize_id"/>
                <el-table-column align="center" :label="$t('eventChance.columns.before_num')" width="120" prop="before_num"/>
                <el-table-column align="center" :label="$t('eventChance.columns.num')" width="120" prop="num"/>
                <el-table-column align="center" :label="$t('eventChance.columns.after_num')" width="120" prop="after_num"/>
                <el-table-column align="center" :label="$t('eventChance.columns.remark')" prop="remark"/>
                <el-table-column align="center" :label="$t('eventChance.columns.created_at')" width="160" prop="created_at"/>
            </el-table>
            
            <!-- 添加日志分页组件 -->
            <div class="block" style="margin-top: 20px;">
                <el-pagination
                    background
                    :current-page="logPaginationData.page"
                    :page-sizes="[10, 20, 50, 100]"
                    :page-size="logPaginationData.size"
                    layout="total, sizes, prev, pager, next, jumper"
                    :total="logPaginationData.total"
                    @size-change="handleLogSizeChange"
                    @current-change="handleLogCurrentChange"
                />
            </div>
        </el-dialog>
    </div>
</template>

<script>
import { getChanceList, addChance, getChanceLog } from '@/api/event_chance'

export default {
    name: 'EventChance',
    data() {
        return {
            chanceList: [],
            logList: [],
            addDialogVisible: false,
            logDialogVisible: false,
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            chanceForm: {
                user_id: '',
                num: '',
                remark: ''
            },
            formItemList: [
                {
                    label: this.$t('eventChance.search.user_id'),
                    type: 'input',
                    param: 'user_id'
                }
            ],
            logPaginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            currentUserId: null,
        }
    },
    created() {
        this.getData()
    },
    methods: {
        async getData(params) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            const data = {
                page: this.paginationData.page,
                size: this.paginationData.size,
                searchData: this.params
            }
            
            try {
                const res = await getChanceList(data)
                this.chanceList = res.data
                this.paginationData.total = res.total
            } catch (error) {
                console.error(error)
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
        
        handleAddChance() {
            this.chanceForm = {
                user_id: '',
                num: '',
                remark: ''
            }
            this.addDialogVisible = true
        },
        
        async confirmAddChance() {
            if (!this.chanceForm.user_id || !this.chanceForm.num) {
                this.$message({
                    type: 'warning',
                    message: this.$t('eventChance.message.required')
                })
                return
            }
            
            try {
                await addChance(this.chanceForm)
                this.$message({
                    type: 'success',
                    message: this.$t('eventChance.message.addSuccess')
                })
                this.addDialogVisible = false
                this.getData()
            } catch (error) {
                console.error(error)
            }
        },
        
        async handleViewLog(scope) {
            this.currentUserId = scope.row.user_id
            this.logPaginationData.page = 1
            await this.getLogData()
            this.logDialogVisible = true
        },
        
        async getLogData() {
            try {
                const res = await getChanceLog({
                    user_id: this.currentUserId,
                    page: this.logPaginationData.page,
                    size: this.logPaginationData.size
                })
                this.logList = res.data
                this.logPaginationData.total = res.total
            } catch (error) {
                console.error(error)
            }
        },
        
        handleLogSizeChange(val) {
            this.logPaginationData.size = val
            this.getLogData()
        },
        
        handleLogCurrentChange(val) {
            this.logPaginationData.page = val
            this.getLogData()
        }
    }
}
</script> 