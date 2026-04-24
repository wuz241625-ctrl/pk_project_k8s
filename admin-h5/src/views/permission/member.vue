<template>
  <div class="app-container">
    <el-button type="primary" @click="handleAddMember">{{ $t('member.form.addMember') }}</el-button>

    <el-table :data="membersList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('member.form.id')" width="220">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('member.form.account')" width="220">
        <template slot-scope="scope">
          {{ scope.row.account }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('member.form.name')" width="220">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="header-center" show-overflow-tooltip :label="$t('member.form.googleKey')">
        <template slot-scope="scope">
          {{ scope.row.ggkey }}
        </template>
      </el-table-column>
      <el-table-column align="header-center" :label="$t('member.form.role')">
        <template slot-scope="scope">
          {{ rolesList.filter(item => item.id === scope.row.role).map(item => item.name)[0]}}
        </template>
      </el-table-column>
      <el-table-column align="header-center" :label="$t('member.form.updateTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_update }}
        </template>
      </el-table-column>
      <el-table-column align="header-center" :label="$t('member.form.createTime')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('member.form.operation')" width="300">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('member.form.edit') }}</el-button>
          <el-button
            :type="scope.row.status === 0 ? 'warning' : 'success'"
            size="small"
            @click="handleChangeStatus(scope)"
          >
            {{ scope.row.status === 1 ? $t('member.form.disable') : $t('member.form.enable') }}
          </el-button>
          <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('member.form.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('member.form.edit') : $t('member.form.addMember')" :close-on-click-modal="false">
      <el-form :model="member" label-width="80px" label-position="left">
        <el-form-item :label="$t('member.form.account')">
          <el-input v-model="member.account" :placeholder="$t('member.form.account')" />
        </el-form-item>
        <el-form-item :label="$t('member.form.name')">
          <el-input v-model="member.name" :placeholder="$t('member.form.name')" />
        </el-form-item>
        <el-form-item :label="$t('member.form.role')">
          <el-select v-model="member.role" :placeholder="$t('member.form.rolePlaceholder')">
            <el-option
              v-for="role in currentUserRoleList"
              :key="role.id"
              :label="role.name"
              :value="role.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('member.form.promotionId')" v-if="member.role === 19">
          <el-input v-model="member.parent_id" :placeholder="$t('member.form.promotionId')" />
        </el-form-item>
        <el-tooltip v-model="capsTooltip" :content="$t('member.form.capsLockOn')" placement="right" manual style="max-width: 282px;">
          <el-form-item :label="$t('member.form.password')">
            <el-input
              :key="passwordType"
              ref="password"
              v-model="password"
              :type="passwordType"
              :placeholder="$t('member.form.passwordPlaceholder')"
              tabindex="2"
              autocomplete="on"
              @keyup.native="checkCapslock"
              @blur="capsTooltip = false"
              @keyup.enter.native="handleLogin"
            />
            <span class="show-pwd" @click="showPwd">
              <svg-icon :icon-class="passwordType === 'password' ? 'eye' : 'eye-open'" />
            </span>
          </el-form-item>
        </el-tooltip>
      </el-form>
      <el-button type="warning" size="small" @click="handleResetGg">{{ $t('member.form.resetKey') }}</el-button>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible = false">{{ $t('member.form.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('member.form.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { deepClone } from '@/utils'
import { isSafe } from '@/utils/validate'
import { getRoles,getCurrentUserRole, addMember, getMembers, updateMember, deleteMember, resetGgkey } from '@/api/permission'

const defaultMember = {
    account: '',
    name: '',
    role: '',
    parent_id: null
}

export default {
    data() {
        return {
            member: Object.assign({}, defaultMember),
            rolesList: [],
            currentUserRoleList: [],
            membersList: [],
            dialogVisible: false,
            dialogType: 'new',
            passwordType: 'password',
            capsTooltip: false,
            password: ''
        }
    },
    created() {
        this.getData()
    },
    methods: {
    /* 获取数据*/
        async getData() {
            var res = await getRoles()
            this.rolesList = res.data
            var res = await getCurrentUserRole()
            this.currentUserRoleList = res.data
            res = await getMembers()
            this.membersList = res.data
        },
        cleanData(data) {
            // 移除包含 "a." 或其他类似的字段
            Object.keys(data).forEach(key => {
                if (key.includes('.')) {
                    delete data[key];  // 删除包含 "." 的字段
                }
            });
            return data;
        },
        /* 新增成员*/
        handleAddMember() {
            this.member = Object.assign({}, defaultMember)
            this.member = this.cleanData(this.member);
            this.dialogType = 'new'
            this.dialogVisible = true
            this.password = ''
        },
        /* 编辑成员*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.member = deepClone(scope.row)
            this.member = this.cleanData(this.member);
            delete this.member.created; delete this.member.updated
            this.password = ''
        },
        /* 启用或禁用账号*/
    handleChangeStatus({ $index, row }) {
        const tipsString = row.status === 1 ? this.$t('member.form.disable') : this.$t('member.form.enable');
        this.$confirm(this.$t('method.confirm', { action: tipsString }), this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            var data = { id: row.id, status: Math.abs(row.status - 1) };
            try { await updateMember(data) } catch (err) { return }
            this.$message({
                type: 'success',
                message: this.$t('bankrecord.success', { action: tipsString })
            })
            this.getData()
        }).catch(() => {})
    },
        /* 重置谷歌密钥*/
    handleResetGg() {
        this.$confirm(this.$t('method.resetGg.confirm'), this.$t('method.resetGg.title'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            try { await resetGgkey({ 'id': this.member.id }) } catch (err) { return }
            this.$message({
                type: 'success',
                message: this.$t('method.resetGg.success')
            })
            this.getData()
        }).catch(() => {})
    },
        /* 删除成员*/
    handleDelete({ $index, row }) {
        this.$confirm(this.$t('method.delete.confirm'), this.$t('method.delete.title'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            try { await deleteMember({ 'id': row.id }) } catch (err) { return }
            this.$message({
                type: 'success',
                message: this.$t('method.delete.success')
            })
            this.getData()
        }).catch(() => {})
    },
    checkCapslock(e) {
        const { key } = e
        this.capsTooltip = key && key.length === 1 && (key >= 'A' && key <= 'Z')
    },
    showPwd() {
        if (this.passwordType === 'password') {
            this.passwordType = ''
        } else {
            this.passwordType = 'password'
        }
        this.$nextTick(() => {
            this.$refs.password.focus()
        })
    },
        /* 确认新增或编辑*/
    async confirmRole() {
        var data = this.member
        if (this.password) {
            var message = ''
            if (this.password.length < 6) {
                message = this.$t('method.confirmRole.passwordLength')
            } else if (!isSafe(this.password)) {
                message = this.$t('method.confirmRole.illegalChars')
            }
            if (message) {
                this.$message({
                    type: 'warning',
                    message: message
                })
                return
            } else {
                data.password = this.password
            }
        }
        const isEdit = this.dialogType === 'edit'
        if (isEdit) {
            try { await updateMember(data) } catch (err) { return }
        } else {
            if (this.password) {
                try { await addMember(data) } catch (err) { return }
            } else {
                this.$message({
                    type: 'warning',
                    message: this.$t('method.confirmRole.enterPassword')
                })
                return
            }
            const { account, name, role, parent_id } = this.member
            this.dialogVisible = false
             // 获取标题和消息模板的翻译
            const title = isEdit ? this.$t('method.notification.success_save') : this.$t('method.notification.success_add');
            const accountText = this.$t('method.notification.details.account');
            const nameText = this.$t('method.notification.details.name');
            const roleText = this.$t('method.notification.details.role');
            const parentIdText = this.$t('method.notification.details.parent_id');

            // 格式化消息内容
            const message = `
                <div>${accountText}: ${account}</div>
                <div>${nameText}: ${name}</div>
                <div>${roleText}: ${role}</div>
                <div>${parentIdText}: ${parent_id}</div>
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
        const { account, name, role } = this.member
        this.dialogVisible = false
        this.$notify({
            title: isEdit ? this.$t('method.confirmRole.saveSuccess') : this.$t('method.confirmRole.addSuccess'),
            dangerouslyUseHTMLString: true,
            message: `
                <div>${this.$t('method.confirmRole.roleIdentifier')}: ${account}</div>
                <div>${this.$t('method.confirmRole.roleName')}: ${name}</div>
                <div>${this.$t('method.confirmRole.roleDescription')}: ${role}</div>
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
    right:10px;
    font-size: 16px;
    cursor: pointer;
    user-select: none;
  }
</style>
