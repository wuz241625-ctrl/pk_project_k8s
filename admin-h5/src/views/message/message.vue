<template>
    <div class="app-container">
        <baseSearch ref="search" :form-item-list="formItemList" @search="getData" @export="getData"/>
        <el-button type="primary" @click="handleAdd">{{ $t('message.button.add') }}</el-button>

        <el-table :data="messageList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('message.columns.id')" width="80">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.subject')" width="200">
                <template slot-scope="scope">
                    {{ scope.row.subject }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.content')" width="300">
                <template slot-scope="scope">
                    {{ scope.row.content }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.type')" width="120">
                <template slot-scope="scope">
                    {{ getMessageType(scope.row.type) }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.to_id')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.to_id || $t('message.status.all_user') }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.from_id')" width="80">
                <template slot-scope="scope">
                    {{ scope.row.from_id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.status')" width="120">
                <template slot-scope="scope">
                    {{ getStatus(scope.row.status) }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.send_time')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.send_time }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.created_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.created_at }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('message.columns.operation')" width="200">
                <template slot-scope="scope">
                    <el-button
                        v-if="scope.row.status === 1"
                        type="primary"
                        size="small"
                        @click="handleEdit(scope)">
                        {{ $t('message.button.edit') }}
                    </el-button>
                    <el-button
                        v-if="scope.row.status === 1"
                        type="success"
                        size="small"
                        @click="handlePublish(scope)">
                        {{ $t('message.button.publish') }}
                    </el-button>
                    <el-button
                        type="danger"
                        size="small"
                        @click="handleDelete(scope)">
                        {{ $t('message.button.delete') }}
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

        <!-- 新增/编辑弹窗 -->
        <el-dialog
            :title="dialogType === 'edit' ? $t('message.dialog.editTitle') : $t('message.dialog.addTitle')"
            :visible.sync="dialogVisible"
            :close-on-click-modal="false"
            width="50%"
        >
            <el-form :model="messageForm" label-width="120px" label-position="left">
                <el-form-item :label="$t('message.form.subject')" required>
                    <el-input
                        v-model="messageForm.subject"
                        :placeholder="$t('message.form.subject_placeholder')"
                        maxlength="100"
                        show-word-limit
                    />
                </el-form-item>

                <el-form-item :label="$t('message.form.content')" required>
                    <el-input
                        v-model="messageForm.content"
                        type="textarea"
                        :rows="4"
                        :placeholder="$t('message.form.content_placeholder')"
                    />
                </el-form-item>

                <el-form-item :label="$t('message.form.type')" required>
                    <el-select v-model="messageForm.type" :placeholder="$t('message.form.type_placeholder')">
                        <el-option :label="$t('message.type.system')" :value="1"/>
                    </el-select>
                </el-form-item>

                <el-form-item :label="$t('message.form.to_id')">
                    <el-input
                        v-model="messageForm.to_id"
                        :placeholder="$t('message.form.to_id_placeholder')"
                    />
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button @click="dialogVisible = false">{{ $t('message.button.cancel') }}</el-button>
                <el-button type="primary" @click="confirmAdd">{{ $t('message.button.confirm') }}</el-button>
            </div>
        </el-dialog>
    </div>
</template>

<script>
import { getMessageList, addMessage, deleteMessage, publishMessage, updateMessage } from '@/api/message'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Message',
    data() {
        return {
            messageList: [],
            dialogVisible: false,
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            messageForm: {
                subject: '',
                content: '',
                type: 1,
                to_id: '',
                send_time: ''
            },
            formItemList: [
                {
                    label: this.$t('message.search.subject'),
                    type: 'input',
                    param: 'subject'
                },
                {
                    label: this.$t('message.search.send_time'),
                    type: 'dateTimePicker',
                    pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
                    param: 'send_time'
                }
            ],
            dialogType: 'add'
        }
    },
    created() {
        this.getData()
    },
    methods: {
        getMessageType(type) {
            return type === 1 ? this.$t('message.type.system') : this.$t('message.type.normal')
        },
        getStatus(status) {
            return status === 1 ? this.$t('message.status.pending') : this.$t('message.status.published')
        },
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
                const res = await getMessageList(data)
                this.messageList = res.data
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

        handleAdd() {
            this.dialogType = 'add'
            this.messageForm = {
                subject: '',
                content: '',
                type: 1,
                to_id: '',
                send_time: new Date()
            }
            this.dialogVisible = true
        },

        async confirmAdd() {
            if (!this.messageForm.subject || !this.messageForm.content) {
                this.$message({
                    type: 'warning',
                    message: this.$t('message.message.required')
                })
                return
            }

            try {
                if (this.dialogType === 'edit') {
                    await updateMessage(this.messageForm)
                    this.$message({
                        type: 'success',
                        message: this.$t('message.message.updateSuccess')
                    })
                } else {
                    await addMessage(this.messageForm)
                    this.$message({
                        type: 'success',
                        message: this.$t('message.message.addSuccess')
                    })
                }
                this.dialogVisible = false
                this.getData()
            } catch (error) {
                console.error(error)
            }
        },

        async handleDelete(scope) {
            try {
                await this.$confirm(
                    this.$t('message.message.deleteConfirm'),
                    this.$t('message.message.warning'),
                    {
                        confirmButtonText: this.$t('message.button.confirm'),
                        cancelButtonText: this.$t('message.button.cancel'),
                        type: 'warning'
                    }
                )

                await deleteMessage({ id: scope.row.id })
                this.$message({
                    type: 'success',
                    message: this.$t('message.message.deleteSuccess')
                })
                this.getData()
            } catch (error) {
                console.error(error)
            }
        },

        async handlePublish(scope) {
            try {
                await this.$confirm(
                    this.$t('message.message.publishConfirm'),
                    this.$t('message.message.warning'),
                    {
                        confirmButtonText: this.$t('message.button.confirm'),
                        cancelButtonText: this.$t('message.button.cancel'),
                        type: 'warning'
                    }
                )

                await publishMessage({ id: scope.row.id })
                this.$message({
                    type: 'success',
                    message: this.$t('message.message.publishSuccess')
                })
                this.getData()
            } catch (error) {
                console.error(error)
            }
        },

        handleEdit(scope) {
            this.dialogType = 'edit'
            this.messageForm = { ...scope.row }
            this.dialogVisible = true
        }
    }
}
</script>
