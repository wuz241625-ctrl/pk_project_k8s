<template>
  <div class="app-container">
    <el-button type="primary" @click="handleAddRole">{{ $t('role.form.addRole') }}</el-button>

    <el-table :data="currentUserRoleList" style="width: 100%; margin-top: 30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('role.form.roleKey')">
        <template slot-scope="scope">
          {{ scope.row.key_name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('role.form.roleName')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" label="Level">
        <template slot-scope="scope">
          {{ scope.row.level }}
        </template>
      </el-table-column>
      <el-table-column align="header-center" :label="$t('role.form.roleDescription')">
        <template slot-scope="scope">
          {{ scope.row.description }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('role.form.parentRole')">
        <template slot-scope="scope">
          {{ getParentRoleName(scope.row.parent_id) }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('role.form.operation')" width="220">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('role.form.edit') }}</el-button>
          <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('role.form.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('role.form.dialogTitleEdit') : $t('role.form.dialogTitleAdd')" :close-on-click-modal="false">
      <el-form :model="role" label-width="80px" label-position="left">
        <el-form-item :label="$t('role.form.roleKey')">
          <el-input v-model="role.key_name" :placeholder="$t('role.form.roleKeyPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('role.form.roleName')">
          <el-input v-model="role.name" :placeholder="$t('role.form.roleNamePlaceholder')" />
        </el-form-item>
        <el-form-item label="Level">
          <template slot-scope="scope">
            <el-select v-model="role.level" placeholder="请选择" style="width: 100px;">
              <el-option
                v-for="item in filteredLevelOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              ></el-option>
            </el-select>
          </template>
        </el-form-item>
        <el-form-item :label="$t('role.form.roleDescription')">
          <el-input v-model="role.description" :autosize="{ minRows: 2, maxRows: 4}" type="textarea" :placeholder="$t('role.form.roleDescriptionPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('role.form.parentRole')">
          <el-select v-model="role.parent_id" placeholder="请选择上级角色" style="width: 100%;">
            <el-option
              v-for="item in currentUserRoleList"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            ></el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('role.form.permissions')">
          <el-tree ref="tree" :data="routesData" :props="defaultProps" show-checkbox node-key="id" class="permission-tree" />
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('role.form.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('role.form.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { deepClone } from '@/utils'
import { getPermissions,getCurrentUserRolePermissions, getRoles, getCurrentUserRole, addRole, deleteRole, updateRole } from '@/api/permission'

const defaultRole = {
    key_name: '',
    name: '',
    description: '',
    permissions: [],
    parent_id: null
}

export default {
    data() {
        return {
            role: Object.assign({}, defaultRole),
            permissions: [], // 权限树形表
            rolesList: [], // 角色列表
            currentUserRoleList: [],
            dialogVisible: false,
            dialogType: 'new',
            checkedIds: [], // 可直选无分支的权限
            defaultProps: {
                children: 'children',
                label: 'name'
            },
            level: '',
            // Level 的字典配置
            levelOptions: [
              { label: "Level 1", value: 1 },
              { label: "Level 2", value: 2 },
              { label: "Level 3", value: 3 },
              { label: "Level 4", value: 4 },
              { label: "Level 5", value: 5 },
            ],
        }
    },
    computed: {
        routesData() {
            return this.permissions
        },
        filteredLevelOptions() {
          // 如果当前 Level 为 3，仅显示 3、4、5
          if (this.level !== 0) {
            return this.levelOptions.filter(option => option.value >= this.level);
        }
          // 否则显示全部
          return this.levelOptions;
        },
    },
    created() {
        this.getData()
    },
    methods: {
    /* 获取数据*/
        async getData() {
            var res = await getCurrentUserRolePermissions()
            this.permissions = this.generatePermissions(res.data)
            res = await getRoles()
            this.rolesList = res.data
            res = await getCurrentUserRole()
            this.currentUserRoleList = res.data
            this.level = res.level
        },
        /* 编辑树形数据*/
        generatePermissions(permissions) {
            const res = []
            const fn = (permissions, parent) => {
                parent.children = []
                permissions.forEach((permission) => {
                    if (permission.pid === parent.id && permission.id !== parent.id) {
                        permission = fn(permissions, permission)
                        parent.children.push(permission)
                    }
                })
                if (parent.children.length === 0) {
                    this.checkedIds.push(parent.id.toString())
                }
                return parent
            }
            // 查找子级
            for (var permission of permissions) {
                if (permission.id === permission.pid) {
                    permission = fn(permissions, permission)
                    res.push(permission)
                }
            }
            return res
        },
        /* 新增角色*/
        handleAddRole() {
            this.role = Object.assign({}, defaultRole)
            if (this.$refs.tree) {
                this.$refs.tree.setCheckedNodes([])
            }
            this.dialogType = 'new'
            this.dialogVisible = true
        },
        /* 编辑角色*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.checkStrictly = false
            this.role = deepClone(scope.row)
            this.$nextTick(() => {
                this.$refs.tree.setCheckedKeys(this.role.permissions.split(',').filter(item => this.checkedIds.includes(item)))
            })
        },
        /* 删除角色*/
        handleDelete({ $index, row }) {
            this.$confirm(this.$t('method.roleDelete.confirm'), this.$t('method.roleDelete.title'), {
                type: 'warning',
                confirmButtonText: this.$t('method.confirm'),
                cancelButtonText: this.$t('method.cancel')
            }).then(async () => {
                try { await deleteRole({ 'id': row.id }) } catch (err) { return }
                this.$message({
                    type: 'success',
                    message: this.$t('method.roleDelete.success')
                });
                this.getData();
            }).catch(() => {});
        },
        /* 获取上级角色名称*/
        getParentRoleName(parentId) {
          console.log("parentId",parentId)
          console.log("this.rolesList",this.rolesList)
            const parentRole = this.rolesList.find(role => role.id === parentId);
            return parentRole ? parentRole.name : '无';
        },
        /* 确认新增或编辑*/
    async confirmRole() {
        var data = this.role;
        const isEdit = this.dialogType === 'edit';
        data.permissions = (this.$refs.tree.getHalfCheckedKeys().concat(this.$refs.tree.getCheckedKeys())).toString();
        data.parent_id = this.role.parent_id;
        if (isEdit) {
            try { await updateRole(data) } catch (err) { return }
        } else {
            try { await addRole(data) } catch (err) { return }
        }
        const { description, key_name, name } = this.role;
        this.dialogVisible = false;
        this.$notify({
            title: isEdit ? this.$t('method.roleSave.saveSuccess') : this.$t('method.roleSave.addSuccess'),
            dangerouslyUseHTMLString: true,
            message: `
                <div>${this.$t('method.roleSave.keyName')}: ${key_name}</div>
                <div>${this.$t('method.roleSave.name')}: ${name}</div>
                <div>${this.$t('method.roleSave.description')}: ${description}</div>
            `,
            type: 'success'
        });
        this.getData();
    }
  }
}
</script>

<style lang="scss" scoped>
.permission-tree {
    margin-bottom: 30px;
  }
</style>
