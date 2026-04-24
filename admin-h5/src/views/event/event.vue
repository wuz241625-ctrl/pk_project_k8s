<!--suppress ES6ShorthandObjectProperty -->
<template>
    <div class="app-container">
        <baseSearch
            ref="search"
            :form-item-list="formItemList"
            @search="getData"
            @export="getData"
        />
        <el-button type="primary" @click="handleAddMember">{{ $t('event.button.add') }}</el-button>

        <el-table :data="membersList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('event.columns.id')" width="150">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('event.columns.title')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.title }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('event.columns.content')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.content }}
                </template>
            </el-table-column>
            <el-table-column align="header-center" :label="$t('event.columns.type')" width="160">
                <template slot-scope="scope">
                    {{ getTypeName(scope.row.type) }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('event.columns.participant')" width="120">
                <template slot-scope="scope">
                    {{ scope.row.participant === '-1' ? $t('event.status.all_user') : scope.row.participant }}
                </template>
            </el-table-column>

            <el-table-column align="center" label="图片" width="220">
                <template slot-scope="scope">
                    <img :src="'/upload/' + scope.row.pic" alt="活动图片" width="50" height="50" />
                </template>
            </el-table-column>

            <!-- <el-table-column align="header-center" label="更新时间" width="160">
              <template slot-scope="scope">
                {{ scope.row.updated_at }}
              </template>
            </el-table-column> -->

            <el-table-column align="header-center" :label="$t('event.columns.status')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.status === 1 ? $t('event.status.enable') : $t('event.status.disable') }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('event.columns.is_app_show')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.is_app_show === 1 ? $t('event.is_app_show.enable') : $t('event.is_app_show.disable') }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('event.columns.begin_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.begin_at }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('event.columns.end_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.end_at }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('event.columns.created_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.created_at }}
                </template>
            </el-table-column>

            <el-table-column align="center" label="操作" width="300">
                <template slot-scope="scope">
                    <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('event.button.edit') }}</el-button>
                    <el-button
                        :type="scope.row.status === 0 ? 'warning' : 'success'"
                        size="small"
                        @click="handleChangeStatus(scope)"
                    >
                        {{ scope.row.status === 1 ? $t('event.button.disable') : $t('event.button.enable') }}
                    </el-button>
                    <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('event.button.delete') }}</el-button>
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

        <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('event.button.edit') : $t('event.button.add')" :close-on-click-modal="false">
            <el-form :model="event" label-width="80px" label-position="left">

                <div style="display: none;">
                    <el-form-item :label="$t('event.form.id')">
                        <el-input v-model="event.id" :placeholder="$t('event.form.id_placeholder')"/>
                    </el-form-item>
                </div>

                <el-form-item :label="$t('event.form.title')">
                    <el-input
                        v-model="event.title"
                        :placeholder="$t('event.form.title_placeholder')"
                        maxlength="50"
                        show-word-limit
                        required
                    />
                </el-form-item>

                <el-form-item :label="$t('event.form.type')">
                    <el-select v-model="event.type" :placeholder="$t('event.form.type_placeholder')"  @change="handleTypeChange">
                        <el-option label="抽奖" :value="0"/>
                        <el-option label="订单金额满赠" :value="1"/>
                        <el-option label="订单单数满赠" :value="2"/>
                        <el-option label="新手活动" :value="3"/>
                    </el-select>
                </el-form-item>

                <el-form-item label="订单抽奖机会设置"  v-show="event_type == 0 ">
                    <el-input-number
                        v-model="event.lottery_chance_setting"
                        placeholder="多少订单可获得一次抽奖机会"
                        size="large"
                        :min="1"
                    />
                </el-form-item>

                <el-form-item :label="$t('event.form.participant')">
                    <el-input
                        v-model="event.participant"
                        :placeholder="$t('event.form.participant_placeholder')"
                        maxlength="50"
                        show-word-limit
                        required
                    />
                </el-form-item>

                <el-form-item label="上传图片">
                    <el-upload
                        :action="baseUrl + '/files/upload?code=' + randomUploadCode"
                        accept="image"
                        name="image"
                        :limit="1"
                        :on-success="updateSuccess"
                        :on-error="updateError"
                    >
                        <el-button size="small" type="primary">点击上传</el-button>
                        <div slot="tip" class="el-upload__tip">{{ $t('method.df.receipt.justOneFile') }}</div>
                    </el-upload>
                </el-form-item>

                <el-form-item :label="$t('event.form.status')">
                    <el-select v-model="event.status" :placeholder="$t('event.form.status_placeholder')">
                        <el-option :label="$t('event.button.enable')" :value="1"/>
                        <el-option :label="$t('event.button.disable')" :value="0"/>
                    </el-select>
                </el-form-item>
                <el-form-item :label="$t('event.form.is_app_show')">
                    <el-select v-model="event.is_app_show" :placeholder="$t('event.form.is_app_show_placeholder')">
                        <el-option :label="$t('event.is_app_show.enable')" :value="1"/>
                        <el-option :label="$t('event.is_app_show.disable')" :value="0"/>
                    </el-select>
                </el-form-item>

                <el-form-item :label="$t('event.form.begin_at')">
                    <el-date-picker
                        v-model="event.begin_at"
                        type="datetime"
                        :placeholder="$t('event.form.begin_at_placeholder')"
                        style="width: 100%;"
                    />
                </el-form-item>

                <el-form-item :label="$t('event.form.end_at')">
                    <el-date-picker
                        v-model="event.end_at"
                        type="datetime"
                        :placeholder="$t('event.form.end_at_placeholder')"
                        style="width: 100%;"
                    />
                </el-form-item>
                <el-form-item :label="$t('event.form.content')">
                    <!-- <el-input type="textarea" v-model="event.content" :placeholder="$t('event.form.content_placeholder')"
                    maxlength="250"
                    show-word-limit
                    required/> -->
                    <editor v-model="event.content" :init="init"/>
                </el-form-item>

            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="dialogVisible = false">{{ $t('member.form.cancel') }}</el-button>
                <el-button type="danger" @click="confirmRole">{{ $t('member.form.confirm') }}</el-button>
            </div>
        </el-dialog>
    </div>
</template>

<script>
/* eslint-disable no-unused-vars */
import {updateevent, getevents, addevent, deleteevent} from '@/api/event'
import tinymce from 'tinymce/tinymce.js'
// 外觀
import 'tinymce/skins/ui/oxide/skin.css'
import 'tinymce/themes/silver'

// Icon
import 'tinymce/icons/default'

import 'tinymce/plugins/emoticons'
import 'tinymce/plugins/emoticons/js/emojis.js'
import 'tinymce/plugins/table'
import 'tinymce/plugins/quickbars'

// 语言包
// import 'tinymce-i18n/langs/zh_CN.js'
// TinyMCE-Vue
import Editor from '@tinymce/tinymce-vue'

const defaultEvent = {
    id: null, // 活动ID
    title: '', // 标题
    content: '', // 内容
    type: 1, // 活动类型
    participant: '', // 参与人员
    pic: '', // 图片路径
    created_at: '', // 创建时间
    updated_at: '', // 更新时间
    status: 1, // 状态，默认为启用
    is_app_show: 0,               // 是否在app显示
    begin_at: '', // 起始时间
    end_at: '', // 结束时间
    lottery_chance_setting: '' // 抽奖机会设置

}

export default {
    components: {
        Editor
    },
    props: {
        value: {
            type: String,
            default: ''
        },
        plugins: {
            type: [String, Array],
            default: 'quickbars emoticons table'
        },
        toolbar: {
            type: [String, Array],
            default:
                ' bold italic underline strikethrough | fontsizeselect | forecolor backcolor | alignleft aligncenter alignright alignjustify|bullist numlist |outdent indent blockquote | undo redo | axupimgs | removeformat | emoticons |table'
        }
    },
    data() {
        return {
            event: Object.assign({}, defaultEvent),
            rolesList: [],
            randomUploadCode: null,
            baseUrl: process.env.VUE_APP_BASE_API,
            membersList: [],
            order_field: 'id',
            sort: 'desc',
            params: {},
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            dialogVisible: false,
            dialogType: 'new',
            password: '',
            formItemList: [
                {
                    label: '标题',
                    type: 'input',
                    param: 'title'
                }
            ],
            event_type: 1,
            init: {
                height: 200,
                menubar: false,
                content_css: false,
                skin: false,
                plugins: this.plugins,
                toolbar: this.toolbar,
                quickbars_insert_toolbar: false,
                branding: false
            }
        }
    },
    watch: {
        value(newValue) {
            this.event.content = newValue
        },
        editorValue(newValue) {
            this.$emit('input', newValue)
        }
    },
    mounted() {
        tinymce.init({})
    },
    created() {
        this.getData()
        this.randomUploadCode = Math.random().toString(36).substr(2, 9)
    },

    methods: {
        // 根据 type 返回对应的文本
        getTypeName(type) {
            switch (type) {
                case 0:
                    return '抽奖'
                case 1:
                    return '订单金额满赠'
                case 2:
                    return '订单单数满赠'
                case 3:
                    return '新手活动'
                default:
                    return '未知'
            }
        },
        /* 获取数据*/
        async getData(params = null) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }

            var data = {
                order_field: this.order_field,
                sort: this.sort,
                serchData: this.params
            }
            data.size = this.paginationData.size
            data.page = this.paginationData.page

            var res = await getevents(data)
            this.membersList = res.data
            this.paginationData.total = res.total
        },
        handleTypeChange(val) {
            this.event_type = val;
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
        /* 上传成功 */
        updateSuccess(response, file) {
            // Assuming `response` contains the response from your server
            // Example: { path: '/static/upload/filename.jpg' }
            console.log('Upload success:', response)
            // Update the `event.pic` with the path of the uploaded image
            this.event.pic = response.path // Adjust according to your actual response structure
            console.log("this.event",this.event)
            // Notify user of the successful upload
            this.$notify({
                title: '上传成功',
                message: '图片上传成功！',
                type: 'success'
            })
        },
        updateError(err, file) {
            console.error('Upload error:', err)

            // Notify user of the upload failure
            this.$notify({
                title: '上传失败',
                message: '图片上传失败，请重试。',
                type: 'error'
            })
        },
        /* 新增成员*/
        handleAddMember() {
            this.event = Object.assign({}, defaultEvent)
            this.dialogType = 'new'
            this.dialogVisible = true
        },
        /* 编辑成员*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.event = {...scope.row} // 将 scope.row 的内容复制到 this.event
        },
        /* 启用或禁用账号*/
        handleChangeStatus({$index, row}) {
            const tipsString = '确定操作?'
            this.$confirm(this.$t('method.confirm', {action: tipsString}), this.$t('method.warning'), {
                type: 'warning',
                confirmButtonText: this.$t('method.confirm'),
                cancelButtonText: this.$t('method.cancel')
            }).then(async () => {
                var data = {id: row.id, status: Math.abs(row.status - 1)}
                try {
                    await updateevent(data)
                } catch (err) {
                    return
                }
                this.$message({
                    type: 'success',
                    message: this.$t('bankrecord.success', {action: tipsString})
                })
                this.getData()
            }).catch(() => {
            })
        },
        /* 删除成员*/
        handleDelete({$index, row}) {
            this.$confirm('确定删除?', this.$t('method.delete.title'), {
                type: 'warning',
                confirmButtonText: this.$t('method.confirm'),
                cancelButtonText: this.$t('method.cancel')
            }).then(async () => {
                try {
                    await deleteevent({'id': row.id})
                } catch (err) {
                    return
                }
                this.$message({
                    type: 'success',
                    message: this.$t('method.delete.success')
                })
                this.getData()
            }).catch(() => {
            })
        },
        convertToMySQLDatetime(isoString) {
            // Convert ISO 8601 string to a Date object
            const date = new Date(isoString)

            // Check if the date is valid
            if (isNaN(date.getTime())) {
                this.$message({
                    type: 'error',
                    message: '无效的日期格式'
                })
                return ''
            }

            // Format to MySQL DATETIME format
            const year = date.getFullYear()
            const month = String(date.getMonth() + 1).padStart(2, '0') // Months are zero-based
            const day = String(date.getDate()).padStart(2, '0')
            const hours = String(date.getHours()).padStart(2, '0')
            const minutes = String(date.getMinutes()).padStart(2, '0')
            const seconds = String(date.getSeconds()).padStart(2, '0')

            return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
        },
        /* 确认新增或编辑*/
        async confirmRole() {
            var data = this.event
            const isEdit = this.dialogType === 'edit'

            const {title, content, pic, status, begin_at, end_at, type, participant, lottery_chance_setting} = this.event

            console.log('this.event', this.event)
            // Check for empty fields
            if (!title || !content || status === null || !begin_at || !end_at || type === null || !participant) {
                this.$message({
                    type: 'warning',
                    message: '参数不能为空'
                })
                return // Prevent submission
            }

            if(type == 0 && !lottery_chance_setting){
                this.$message({
                    type: 'warning',
                    message: '抽奖机会设置不能为空'
                })
                return // Prevent submission
            }

            this.event.begin_at = this.convertToMySQLDatetime(begin_at)
            this.event.end_at = this.convertToMySQLDatetime(end_at)

            if (begin_at > end_at) {
                this.$message({
                    type: 'warning',
                    message: '开始时间大于结束时间'
                })
                return
            }

            if (isEdit) {
                try {
                    await updateevent(data)
                } catch (err) {
                    return
                }
            } else {
                try {
                    await addevent(data)
                } catch (err) {
                    return
                }
            }
            this.dialogVisible = false
            this.$notify({
                title: isEdit ? this.$t('method.confirmRole.saveSuccess') : this.$t('method.confirmRole.addSuccess'),
                dangerouslyUseHTMLString: true,
                message: `
                <div>标题: ${title}</div>
                <div>内容: ${content}</div>
                <div>活动类型: ${this.getTypeName(type)}</div>
                <div>状态: ${status === 1 ? '启用' : '禁用'}</div>
                <div>起始时间: ${this.event.begin_at}</div>
                <div>结束时间: ${this.event.end_at}</div>
            `,
                type: 'success'
            })
            this.getData()
        }
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
<style>
.tox-tinymce-aux {
    z-index: 2009 !important;
}
</style>
