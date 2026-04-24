<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" @search="getData" />
    <el-button type="primary" @click="handleAdd">{{ $t('method.Yhgl.form.addSetting') }}</el-button>
    <el-table
      :data="bankTypeList"
            style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('method.Yhgl.form.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.Yhgl.form.bank_id')">
        <template slot-scope="scope">
          {{ scope.row.bank_id }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.Yhgl.form.bankName')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.Yhgl.form.type')">
        <template slot-scope="scope">
          {{ scope.row.type === 1 ? $t('method.Yhgl.form.external') : $t('method.Yhgl.form.internal') }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.Yhgl.form.max_order_count')">
        <template slot-scope="scope">
          {{ scope.row.max_count }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.Yhgl.form.accept_interval')">
        <template slot-scope="scope">
          {{ scope.row.max_sec }}
        </template>
      </el-table-column>

      <el-table-column align="center" :label="$t('method.Yhgl.form.status')">
        <template slot-scope="scope">
          {{ scope.row.status === 1 ? $t('method.Yhgl.form.enable') : $t('method.Yhgl.form.disable') }}
        </template>
      </el-table-column>

      <el-table-column fixed="right" align="center" :label="$t('method.Yhgl.form.operation')" width="300">
        <template slot-scope="scope">
          <el-button
            :type="scope.row.status === 0 ? 'warning' : 'success'"
            size="small"
            @click="handleChangeStatus(scope)"
          >
            {{ scope.row.status === 1 ? $t('method.Yhgl.form.disable') : $t('method.Yhgl.form.enable') }}
          </el-button>
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('method.Yhgl.form.edit') }}</el-button>
        </template>
      </el-table-column>

    </el-table>
    <el-dialog
        :visible.sync="dialogVisible"
        :title="dialogType === 'edit' ? $t('method.Yhgl.form.edit') : $t('method.Yhgl.form.addSetting')"
        :close-on-click-modal="false"
      >
        <el-form :model="bankType" label-width="140px" label-position="left">
         
          <!-- 银行下拉选择框 -->
          <el-form-item :label="$t('method.Yhgl.form.bankName')">
            <el-select
              v-model="bankTypeSetting.bank_id"
              placeholder="请选择银行"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="item in bank_type"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item :label="$t('method.Yhgl.form.max_order_count')">
            <el-input-number v-model="bankTypeSetting.max_count" :min="1" />
          </el-form-item>

          <el-form-item :label="$t('method.Yhgl.form.accept_interval')">
            <el-input-number v-model="bankTypeSetting.max_sec" :min="1" />
          </el-form-item>

          <el-form-item :label="$t('method.Yhgl.form.status')">
            <el-switch
              v-model="bankTypeSetting.status"
              :active-value="1"
              :inactive-value="0"
              active-color="#13ce66"
            >
              <span slot="open">{{ $t('method.Yhgl.form.enable') }}</span>
              <span slot="close">{{ $t('method.Yhgl.form.disable') }}</span>
            </el-switch>
          </el-form-item>

        </el-form>

        <div style="text-align:right;">
          <el-button @click="dialogVisible = false">{{ $t('method.Yhgl.form.cancel') }}</el-button>
          <el-button type="primary" @click="confirmRole">{{ $t('method.Yhgl.form.confirm') }}</el-button>
        </div>
      </el-dialog>

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
import {
    deepClone
} from '@/utils'
import {
    getBank_type,
    addBankTypeSetting, deleteBankType,
    getBankTypeSetting, updateBankTypeStatusSetting, updateBankTypeSetting
} from '@/api/partner'

export default {
    name: 'Yhgl',
    data() {
        return {
            bank_type: [],
            newBankType: 0,
            bankTypeSetting: {},
            bankTypeList: [],
            dialogVisible: false,
            dialogType: 'new',
            changeBalance: {},
            formItemList: [
            {
              label: this.$t('method.Yhgl.ds.form.status'),
              type: 'select',
              param: 'status',
              selectOptions: [
                {
                  value: 0,
                  label: this.$t('method.Yhgl.ds.statusType.disabled')
                },
                {
                  value: 1,
                  label: this.$t('method.Yhgl.ds.statusType.enabled')
                }
              ]
            },
            {
                label: this.$t('method.Yhgl.form.bankName'),
                type: 'input',
                param: 'bankName'
            },
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
        this.getBank();
    },
    methods: {
        handleBankChange(row) {
          console.log('选择的银行:', row.bank_type);
          // 可在此调用接口保存或标记为已修改
        },
        /* 获取银行*/
        async getBank(params) {
            const res = await getBank_type()
            this.bank_type = res.data
            console.log('this.bankName==========================', this.$t('method.payment01.ds.table.bankName'))
            // this.bank_type.forEach(bankType => {
            //     this.formItemList.find(item => item.label === this.$t('method.payment01.ds.table.bankName')).selectOptions.push({
            //         value: bankType.id,
            //         label: bankType.name
            //     })
            // })
            // console.log('this.bank_type==========================', this.bank_type)
            // this.getData()
        },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
                this.paginationData.size = 10
            }
            var data = {}
            data.serchData = this.params
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            const res = await getBankTypeSetting(data)
            this.bankTypeList = res.data
            this.paginationData.total = res.total
            this.newBankType = res.newBankType
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
        /* 新增成员*/
        handleAdd() {
            this.dialogType = 'new'
            this.dialogVisible = true
            this.bankType = {}
        },
        /* 编辑码商*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.bankTypeSetting = deepClone(scope.row)
            this.changeBalance = {}
        },
        /* 改变状态*/
    handleChangeStatus({ $index, row }) {
        const tipsString = row.status === 1 ? this.$t('method.disable') : this.$t('method.enable')
        this.$confirm(this.$t('method.confirm_action_setting', { action: tipsString }), 'Warning', {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            var data = {}
            data.id = row.id
            data.status = Math.abs(row.status - 1)
            try {
                await updateBankTypeStatusSetting(data)
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: tipsString + this.$t('method.success')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 删除成员 */
    handleDelete({ $index, row }) {
        this.$confirm(this.$t('method.confirm_delete_bank'), this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            try {
                await deleteBankType({
                    'id': row.id,
                    'is_del': true
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.delete_success')
            })
            this.getData()
        }).catch(() => {})
    },
    /* 确认编辑 */
    async confirmRole() {
        var data = {}
        console.log('bankTypeSetting======================================', this.bankTypeSetting)
        data.id = this.bankTypeSetting.id
        data.bank_id = this.bankTypeSetting.bank_id
        data.max_count = this.bankTypeSetting.max_count
        data.max_sec = this.bankTypeSetting.max_sec
        data.status = this.bankTypeSetting.status
        try {
            if (this.dialogType === 'edit') {
                await updateBankTypeSetting(data)
            } else {
                await addBankTypeSetting(data)
            }
        } catch (err) {
            return
        }
        const { id, name } = this.bankTypeSetting
        this.dialogVisible = false
        this.$notify({
            title: this.$t('method.save_success'),
            dangerouslyUseHTMLString: true,
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
