<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" @search="getData" />
    <el-button type="primary" @click="handleAdd">{{ $t('method.Yhgl.form.addBank') }}</el-button>
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
      <el-table-column align="center" :label="$t('method.Yhgl.form.onlineCount')">
        <template slot-scope="scope">
          {{ scope.row.payment_count_in_orders_ds === undefined ? 0 : scope.row.payment_count_in_orders_ds }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yhgl.form.bankName')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yhgl.form.url')">
        <template slot-scope="scope">
          {{ scope.row.url }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yhgl.form.type')">
        <template slot-scope="scope">
          {{ scope.row.type === 1 ? $t('method.Yhgl.form.external') : $t('method.Yhgl.form.internal') }}
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
          <!-- <el-button type="danger" size="small" @click="handleDelete(scope)">{{ $t('method.Yhgl.form.delete') }}</el-button> -->
        </template>
      </el-table-column>
    </el-table>
    <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('method.Yhgl.form.edit') : $t('method.Yhgl.form.addBank')" :close-on-click-modal="false">
      <el-form :model="bankType" label-width="115px" label-position="left">
        <el-form-item :label="$t('method.Yhgl.form.bankName')">
          <el-input v-model="bankType.name" :placeholder="$t('method.Yhgl.form.placeholderBankName')" />
        </el-form-item>
        <el-form-item :label="$t('method.Yhgl.form.url')">
          <el-input v-model="bankType.url" :placeholder="$t('method.Yhgl.form.placeholderURL')" />
        </el-form-item>
        <el-form-item :label="$t('method.Yhgl.form.type')">
          <el-switch v-model="bankType.type" :active-value="0" :inactive-value="1" active-color="#13ce66">
            <span slot="open">{{ $t('method.Yhgl.form.typeInternal') }}</span>
            <span slot="close">{{ $t('method.Yhgl.form.typeExternal') }}</span>
          </el-switch>
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible = false">{{ $t('method.Yhgl.form.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('method.Yhgl.form.confirm') }}</el-button>
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
    addBankType, deleteBankType,
    getBankType, updateBankType, updateBankTypeStatus
} from '@/api/partner'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Yhgl',
    data() {
        return {
            newBankType: 0,
            bankType: {},
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
              label: this.$t('method.Yhgl.ds.form.online'),
              type: 'select',
              param: 'online',
              selectOptions: [
                {
                  value: 1,
                  label: this.$t('method.Yhgl.ds.onlineOptions.collection')
                },
                {
                  value: 2,
                  label: this.$t('method.Yhgl.ds.onlineOptions.payment')
                }
              ]
            },
            {
              label: this.$t('method.Yhgl.ds.form.time_accept'),
              type: 'dateTimePicker',
              pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
              param: 'time_accept'
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
            const res = await getBankType(data)
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
            this.bankType = deepClone(scope.row)
            this.changeBalance = {}
        },
        /* 改变状态*/
    handleChangeStatus({ $index, row }) {
        const tipsString = row.status === 1 ? this.$t('method.disable') : this.$t('method.enable')
        this.$confirm(this.$t('method.confirm_action', { action: tipsString }), 'Warning', {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            var data = {}
            data.id = row.id
            data.status = Math.abs(row.status - 1)
            try {
                await updateBankTypeStatus(data)
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
        data.id = this.bankType.id
        data.name = this.bankType.name
        data.url = this.bankType.url
        data.type = this.bankType.type
        try {
            if (this.dialogType === 'edit') {
                await updateBankType(data)
            } else {
                await addBankType(data)
            }
        } catch (err) {
            return
        }
        const { id, name } = this.bankType
        this.dialogVisible = false
        this.$notify({
            title: this.$t('method.save_success'),
            dangerouslyUseHTMLString: true,
            message: `
            <div>ID: ${id}</div>
            <div>${this.$t('method.name')}: ${name}</div>
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
