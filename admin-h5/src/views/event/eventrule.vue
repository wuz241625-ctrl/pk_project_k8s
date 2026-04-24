<template>
    <div class="app-container">

        <baseSearch ref="search" :form-item-list="formItemList"
                    @search="getData" @export="getData"/>
        <el-button type="primary" @click="handleAddMember">{{ $t('eventRule.button.add') }}</el-button>

        <el-table :data="membersList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
            <el-table-column align="center" :label="$t('eventRule.columns.id')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.prize_id')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.prize_id }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.prize_title')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.prize_title }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.prize_limit_min')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.prize_limit_min || '无' }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.prize_limit_max')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.prize_limit_max || '无' }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.title')" width="220">
                <template slot-scope="scope">
                    {{ scope.row.title }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.prize_type')" width="160">
                <template slot-scope="scope">
                    {{ getPrizetype(scope.row.prize_type) }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.money')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.money }}
                </template>
            </el-table-column>

            <el-table-column align="center" :label="$t('eventRule.columns.ratio')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.ratio }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('eventRule.columns.created_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.created_at }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('eventRule.columns.updated_at')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.updated_at }}
                </template>
            </el-table-column>

            <el-table-column align="header-center" :label="$t('eventRule.columns.status')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.status === 1 ? $t('eventRule.status.enable') : $t('eventRule.status.disable') }}
                </template>
            </el-table-column>

            <el-table-column align="center" label="操作" width="300">
                <template slot-scope="scope">
                    <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('eventRule.button.edit') }}</el-button>
                    <el-button
                        :type="scope.row.status === 0 ? 'warning' : 'success'"
                        size="small"
                        @click="handleChangeStatus(scope)"
                    >
                        {{ scope.row.status === 1 ? $t('eventRule.status.disable') : $t('eventRule.status.enable') }}
                    </el-button>
                    <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('eventRule.button.delete') }}</el-button>
                </template>
            </el-table-column>


        </el-table>


        <div class="block" style="margin-top: 20px;">
            <el-pagination background :current-page="paginationData.page" :page-sizes="[10, 20, 50, 100]"
                           :page-size="paginationData.size" layout="total, sizes, prev, pager, next, jumper"
                           :total="paginationData.total" @size-change="handleSizeChange" @current-change="handleCurrentChange"/>
        </div>

        <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('eventRule.button.edit') : $t('eventRule.button.add')" :close-on-click-modal="false">
            <el-form :model="event_rule" label-width="80px" label-position="left">

                <div style="display: none;">
                    <el-form-item :label="$t('eventRule.form.id')">
                        <el-input v-model="event_rule.id" :placeholder="$t('eventRule.form.id_placeholder')"/>
                    </el-form-item>
                </div>

                <el-form-item :label="$t('eventRule.form.prize_id')">
                    <el-select v-model="event_rule.prize_id" :placeholder="$t('eventRule.form.prize_id_placeholder')"
                               @change="handleRoleChange">
                        <el-option
                            v-for="event in eventList"
                            :key="event.id"
                            :label="event.title"
                            :value="event.id"
                        />
                    </el-select>

                </el-form-item>

                <el-form-item :label="$t('eventRule.form.title')">
                    <el-input v-model="event_rule.title" :placeholder="$t('eventRule.form.title_placeholder')"
                              maxlength="50"
                              show-word-limit
                              required/>
                </el-form-item>
                <el-form-item :label="$t('eventRule.form.prize_type')" v-show="event_type == 0">
                    <el-select v-model="event_rule.prize_type" :placeholder="$t('eventRule.form.prize_type_placeholder')">
                        <el-option label="固定奖励" :value="1"/>
                        <el-option label="奖金池奖励" :value="2"/>
                        <el-option label="幸运奖" :value="3"/>
                    </el-select>
                </el-form-item>

                <el-form-item :label="$t('eventRule.form.money')">
                    <el-input
                        type="number"
                        v-model="event_rule.money"
                        :placeholder="$t('eventRule.form.money_placeholder')"
                        min="0"
                        step="0.01"
                    />
                </el-form-item>

                <el-form-item :label="$t('eventRule.form.prize_limit_min')" v-show="event_type != 0">
                    <el-input
                        type="number"
                        v-model="event_rule.prize_limit_min"
                        :placeholder="$t('eventRule.form.prize_limit_min_placeholder')"
                        min="0"
                        step="1"
                    />
                </el-form-item>

                <el-form-item :label="$t('eventRule.form.prize_limit_max')" v-show="event_type != 0">
                    <el-input
                        type="number"
                        v-model="event_rule.prize_limit_max"
                        :placeholder="$t('eventRule.form.prize_limit_max_placeholder')"
                        min="0"
                        step="1"
                    />
                </el-form-item>

                <el-form-item :label="$t('eventRule.form.ratio')" v-show="event_type == 0">
                    <el-input
                        type="number"
                        v-model="event_rule.ratio"
                        :placeholder="$t('eventRule.form.ratio_placeholder')"
                        min="0"
                        max="1"
                        step="0.01"
                    />
                </el-form-item>

                <el-form-item :label="$t('eventRule.form.status')">
                    <el-select v-model="event_rule.status" :placeholder="$t('eventRule.form.status_placeholder')">
                        <el-option :label="$t('eventRule.status.enable')" :value="1"/>
                        <el-option :label="$t('eventRule.status.disable')" :value="0"/>
                    </el-select>
                </el-form-item>

            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="dialogVisible = false">{{ $t('eventRule.columns.cancel') }}</el-button>
                <el-button type="danger" @click="confirmRole">{{ $t('eventRule.columns.confirm') }}</el-button>
            </div>
        </el-dialog>
    </div>
</template>

<script>
import {updateeventrule, geteventrules, addeventrule, deleteeventrule} from '@/api/eventrule'

const defaultEvent = {
    id: null,                 // 奖励ID
    prize_id: null,          // 活动ID
    prize_title: '',          // 活动标题
    title: '',                // 奖励标题
    prize_limit_min: '',      // 活动触发下限
    prize_limit_max: '',      // 活动触发上限
    money: 0.0,               // 奖励金额
    ratio: 0.0,               // 奖励概率
    created_at: '',           // 创建时间
    updated_at: '',           // 更新时间
    status: 1,                // 状态，默认为启用
    prize_type: 1,                // 奖励类型
}

export default {
    data() {
        return {
            event_rule: Object.assign({}, defaultEvent),
            eventList: [],
            membersList: [],
            dialogVisible: false,
            dialogType: 'new',
            order_field: 'id',
            sort: 'desc',
            selectedEvent: {},
            event_type: 1,
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            },
            formItemList: [
                {
                    label: '奖励标题',
                    type: 'input',
                    param: 'title'
                },
            ]
        }
    },
    created() {
        this.getData()
    },
    methods: {
        // 根据 type 返回对应的文本
        getPrizetype(type) {
            switch (type) {
                case 1:
                    return '固定奖励'
                case 2:
                    return '奖金池奖励'
                case 3:
                    return '幸运奖'
                default:
                    return '未知'
            }
        },
        handleRoleChange(selectedId) {
            const selectedEvent = this.eventList.find(event => event.id === selectedId);
            if (selectedEvent) {
                this.event_rule.prize_title = selectedEvent.title;
                this.selectedEvent = selectedEvent;
                this.event_type = this.selectedEvent.type;
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
        /* 获取数据*/
        async getData(params) {
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

            var res = await geteventrules(data)
            this.membersList = res.data
            this.eventList = res.eventList
            this.paginationData.total = res.total
        },
        /* 新增成员*/
        handleAddMember() {
            this.event_rule = Object.assign({}, defaultEvent)
            this.dialogType = 'new'
            this.dialogVisible = true
        },
        /* 编辑成员*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.event_rule = {...scope.row};  // 将 scope.row 的内容复制到 this.event_rule
            this.handleRoleChange(this.event_rule.prize_id)
        },
        /* 启用或禁用账号*/
        handleChangeStatus({$index, row}) {
            const tipsString = row.status === 1 ? this.$t('member.form.disable') : this.$t('member.form.enable');
            this.$confirm(this.$t('method.confirm', {action: tipsString}), this.$t('method.warning'), {
                type: 'warning',
                confirmButtonText: this.$t('method.confirm'),
                cancelButtonText: this.$t('method.cancel')
            }).then(async () => {
                var data = {id: row.id, prize_id: row.prize_id, status: Math.abs(row.status - 1)};
                try {
                    await updateeventrule(data)
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
            this.$confirm('确认删除?', this.$t('method.delete.title'), {
                type: 'warning',
                confirmButtonText: this.$t('method.confirm'),
                cancelButtonText: this.$t('method.cancel')
            }).then(async () => {
                try {
                    await deleteeventrule({'id': row.id})
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
        /* 确认新增或编辑*/
        async confirmRole() {
            var data = this.event_rule
            const {id, prize_id, prize_title, title, money, ratio, status, prize_limit_min, prize_limit_max,prize_type} = this.event_rule;
            if (!this.selectedEvent) {
                this.$message({
                    type: 'warning',
                    message: '请选择活动'
                });
                return; // Prevent submission
            }

            //根据类型判断参数是否为空
            // Check for empty fields
            if (!title || status === null) {
                this.$message({
                    type: 'warning',
                    message: '标题、状态参数不能为空'
                });
                return; // Prevent submission
            }

            // 不是幸运奖的需要检测money
            if ( prize_type !== 3){
                if (!money) {
                    this.$message({
                        type: 'warning',
                        message: '金额参数不能为空'
                    });
                    return; // Prevent submission
                }
            }

            if (this.event_type == 0) {
                if (!ratio) {
                    this.$message({
                        type: 'warning',
                        message: '抽奖活动的中奖概率参数不能为空'
                    });
                    return; // Prevent submission
                }
            } else {
                if (!prize_limit_min || !prize_limit_max) {
                    this.$message({
                        type: 'warning',
                        message: '活动参与上限、下限参数不能为空'
                    });
                    return; // Prevent submission
                }
                console.log("prize_limit_min", parseFloat(prize_limit_min))
                console.log("prize_limit_max", parseFloat(prize_limit_max))
                console.log("prize_limit_min >= prize_limit_max", parseFloat(prize_limit_min) >= parseFloat(prize_limit_max))
                if (parseFloat(prize_limit_min) >= parseFloat(prize_limit_max)) {
                    this.$message({
                        type: 'warning',
                        message: '活动参与上下限参数异常'
                    });
                    return; // Prevent submission
                }

            }

            const isEdit = this.dialogType === 'edit'
            if (isEdit) {
                try {
                    await updateeventrule(data)
                } catch (err) {
                    return
                }
            } else {
                try {
                    await addeventrule(data)
                } catch (err) {
                    return
                }
                const {title, content, pic, created_at, updated_at, status} = this.event_rule;
                this.dialogVisible = false;

                // 获取标题和消息模板
                const notificationTitle = isEdit ? '保存成功' : '添加成功';
                const prizeIdText = '奖励ID';
                const prizeTitleText = '活动标题';
                const titleText = '奖励标题';
                const moneyText = '奖励金额';
                const ratioText = '奖励概率';
                const statusText = '状态';

                // 格式化消息内容
                const message = `
                <div>${titleText}: ${title}</div>
                <div>${moneyText}: ${money}</div>
                <div>${ratioText}: ${ratio}</div>
                <div>${statusText}: ${status === 1 ? '启用' : '禁用'}</div>
            `;

                // 显示通知
                this.$notify({
                    title: title,
                    dangerouslyUseHTMLString: true,
                    message: message,
                    type: 'success'
                });
                this.getData()
            }

            this.dialogVisible = false
            this.$notify({
                title: isEdit ? this.$t('method.confirmRole.saveSuccess') : this.$t('method.confirmRole.addSuccess'),
                dangerouslyUseHTMLString: true,
                message: `
                  <div>奖励标题: ${title}</div>
                  <div>奖励金额: ${money}</div>
                  <div>奖励概率: ${ratio}</div>
                  <div>状态: ${status === 1 ? '启用' : '禁用'}</div>
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
