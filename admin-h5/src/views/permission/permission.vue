<template>
    <div class="app-container">
      <el-button type="primary" @click="handleaddRight">添加功能</el-button>
  
      <el-table :data="rolesList" style="width: 100%; margin-top: 30px;"  border stripe row-key="id" :tree-props="{ children: 'children', hasChildren: 'hasChildren' }">
        <!-- 权限名称 -->
    <el-table-column prop="name" label="权限名称" align="center"></el-table-column>
  
    <!-- 父级权限 -->
    <el-table-column prop="parent_name" label="父级权限" align="center">
      <template slot-scope="scope">
        {{ scope.row.parent_name || '无' }}
      </template>
    </el-table-column>
  
  
    <!-- 父级权限 -->
    <!-- <el-table-column prop="parent_name" label="父级权限" align="center">
      <template slot-scope="scope">
        {{ scope.row.parent_name || '无' }}
      </template>
    </el-table-column> -->
  
    <!-- API接口路径 -->
    <el-table-column prop="path" label="API接口路径" align="center"></el-table-column>
  
    <!-- 权限类型 -->
    <el-table-column prop="type" label="权限类型" align="center">
      <template slot-scope="scope">
        {{ scope.row.type === 0 ? '页面权限' : '指令权限' }}
      </template>
    </el-table-column>
  
  
    <!-- 级别 -->
    <el-table-column prop="level" label="级别" align="center">
      <template slot-scope="scope">
        {{ scope.row.level || '未知' }} <!-- If level exists, show it; otherwise, show '未知' -->
      </template>
    </el-table-column>
  
    <!-- 状态 -->
    <el-table-column prop="status" label="状态" align="center">
      <template slot-scope="scope">
        <el-tag :type="scope.row.status === 1 ? 'success' : 'danger'">
          {{ scope.row.status === 1 ? '启用' : '禁用' }}
        </el-tag>
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
        <el-form :model="role" label-width="120px" label-position="left">
          <!-- 父级ID -->
          <el-form-item :label="'父级权限ID'">
            <el-input v-model="role.pid" :placeholder="'请输入父级权限ID'" />
          </el-form-item>
        
          <!-- 权限名称 -->
          <el-form-item :label="'权限名称'">
            <el-input v-model="role.name" :placeholder="'请输入权限名称'" />
          </el-form-item>
        
          <!-- API接口路径 -->
          <el-form-item :label="'API接口路径'">
            <el-input v-model="role.path" :placeholder="'请输入API接口路径'" />
          </el-form-item>
        
          <!-- 权限类型 -->
          <el-form-item label="权限类型">
            <template slot-scope="scope">
              <el-select v-model="role.type" placeholder="'请选择权限类型'" style="width: 100px;">
                <el-option label="页面权限" :value="0"></el-option>
                <el-option label="指令权限" :value="1"></el-option>
              </el-select>
            </template>
          </el-form-item>
        
          <!-- 状态 -->
          <el-form-item label="状态">
            <template slot-scope="scope">
              <el-select v-model="role.status" placeholder="请选择状态" style="width: 100px;">
                <el-option label="启用" :value="1"></el-option>
                <el-option label="禁用" :value="0"></el-option>
              </el-select>
            </template>
          </el-form-item>
        
          <!-- 权限等级 -->
           <el-form-item label="权限等级">
            <template slot-scope="scope">
              <el-select v-model="role.level" placeholder="请选择等级" style="width: 100px;">
                <el-option
                  v-for="item in filteredLevelOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                ></el-option>
              </el-select>
            </template>
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
  import { getPermissions, getRight, addRight, deleteRight, updateRight } from '@/api/permission'
  
  const defaultRole = {
  }
  
  export default {
      data() {
          return {
              role: Object.assign({}, defaultRole),
              permissions: [], // 权限树形表
              rolesList: [], // 用户列表
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
         // 将扁平数据构建成树形结构
          buildTree(data) {
            const idMap = {};
            const tree = [];
  
            data.forEach(item => (idMap[item.id] = { ...item, children: [] }));
            data.forEach(item => {
              if (item.pid !== 0) {
                idMap[item.pid]?.children.push(idMap[item.id]);
              } else {
                tree.push(idMap[item.id]);
              }
            });
  
            return tree;
          },
          /* 获取数据*/
          async getData() {
              var res = await getPermissions()
              this.permissions = this.generatePermissions(res.data)
              res = await getRight()
              this.rolesList = res.data
              
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
          handleaddRight() {
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
              // this.$nextTick(() => {
              //     this.$refs.tree.setCheckedKeys(this.role.permissions.split(',').filter(item => this.checkedIds.includes(item)))
              // })
          },
          /* 删除角色*/
      handleDelete({ $index, row }) {
        this.$confirm('确认删除该数据吗？', '删除', {
            type: 'warning',
            confirmButtonText: '确认',
            cancelButtonText: '取消'
        }).then(async () => {
            try {
                await deleteRight({ 'id': row.id });
            } catch (err) {
                return;
            }
            this.$message({
                type: 'success',
                message: '删除成功'
            });
            this.getData();
        }).catch(() => {});
  
      },
          /* 确认新增或编辑*/
      async confirmRole() {
          var data = this.role;
          const isEdit = this.dialogType === 'edit';
          // data.permissions = (this.$refs.tree.getHalfCheckedKeys().concat(this.$refs.tree.getCheckedKeys())).toString();
          if (isEdit) {
              try { await updateRight(data) } catch (err) { return }
          } else {
              try { await addRight(data) } catch (err) { return }
          }
          const { name } = this.role;
          this.dialogVisible = false;
          this.$notify({
              title: isEdit ? '保存成功' : '添加成功',  // 固定的文本，去掉翻译
              dangerouslyUseHTMLString: true,
              message: `
                  <div>名称: ${name}</div>
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
  
    /* 调整 el-select 输入框的高度 */
  .custom-select .el-input__inner {
    height: 24px; /* 输入框高度 */
    line-height: 24px;
    font-size: 12px; /* 字体大小 */
  }
  
  /* 调整下拉框选项的高度 */
  .custom-select .el-select-dropdown__item {
    height: 24px; /* 下拉选项高度 */
    line-height: 24px;
    font-size: 12px;
  }
  </style>