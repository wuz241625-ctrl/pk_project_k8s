<template>
  <div class="app-container">
    <baseSearch
      ref="search"
      :form-item-list="formItemList"
      :export-data="exportData"
      :show-export-tips="false"
      @search="getData"
      @export="getData"
    />
    <el-button type="primary" @click="handleAdd">{{ $t('method.Mslb.buttons.add_partner') }}</el-button>
    <el-button type="success" plain>{{ $t('method.Mslb.buttons.new_partner') }}{{ new_partner }}</el-button>
    <el-button type="primary" plain>{{ $t('method.Mslb.buttons.online_partner') }}{{ online_partner }}</el-button>
    <el-button type="primary" plain>{{ $t('method.Mslb.buttons.online_ds_partner') }}{{ online_ds_partner }}</el-button>
    <el-button type="primary" plain>{{ $t('method.Mslb.buttons.online_df_partner') }}{{ online_df_partner }}</el-button>
    <el-button type="primary" @click="handleClearBalance()">{{ $t('method.Mslb.buttons.clear_balance') }}</el-button>
    <el-table
      :data="partnerList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
      :cell-style="cellStyle" @sort-change="sort_change"   @selection-change="selectionChangeHandlerOrder"
    >
      <el-table-column type="selection"  align="center"  width="50" />
      <el-table-column align="center" :label="$t('method.Mslb.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.phone')">
        <template slot-scope="scope">
          {{ scope.row.cellphone }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.superior_id')">
        <template slot-scope="scope">
          {{ scope.row.pid }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.top_partner_id')">
        <template slot-scope="scope">
          {{ scope.row.top_partner_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.vip')">
        <template slot-scope="scope">
          {{ 'vip' + scope.row.vip }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.balance')" sortable>
        <template slot-scope="scope">
          {{ scope.row.balance }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.frozen_balance')" sortable>
        <template slot-scope="scope">
          {{ scope.row.balance_frozen }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.deposit')" sortable>
        <template slot-scope="scope">
          {{ scope.row.balance_deposit }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.status1')">
        <template slot-scope="scope">
          {{ scope.row.certified === 1 ? $t('method.Mslb.table.status.certified') : $t('method.Mslb.table.status.uncertified') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.external_internal1')">
        <template slot-scope="scope">
          {{ scope.row.type === 1 ? $t('method.Mslb.table.external') : $t('method.Mslb.table.internal') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.registration_time')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.min_ds_limit')" width="160">
        <template slot-scope="scope">
          {{ scope.row.ds_min }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.max_ds_limit')" width="160">
        <template slot-scope="scope">
          {{ scope.row.ds_max }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.invitation_code')" width="160">
        <template slot-scope="scope">
          {{ scope.row.invitation_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Mslb.table.actions')" width="220px">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('method.Mslb.table.edit') }}</el-button>
          <el-button
            :type="scope.row.status === 0 ? 'warning' : 'success'"
            size="small"
            @click="changeStatus(scope, 0)"
          >
            {{ scope.row.status === 0 ? $t('method.Mslb.table.unlock') : $t('method.Mslb.table.lock') }}
          </el-button>
          <el-button type="danger" size="small" @click="migrateEdit(scope)">{{ $t('method.Mslb.table.migrate') }}</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog :visible.sync="dialogVisible" :title="dialogType === 'edit' ? $t('method.Mslb.dialog.edit') : $t('method.Mslb.dialog.add')" :close-on-click-modal="false">
      <el-form :model="partner" label-width="115px" label-position="left">
        <el-form-item :label="$t('method.Mslb.dialog.phone')">
          <el-input v-model="partner.cellphone" :placeholder="$t('method.Mslb.dialog.phone_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.name')">
          <el-input v-model="partner.name" :placeholder="$t('method.Mslb.dialog.name_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.min_ds_limit')">
          <el-input v-model="partner.ds_min" :placeholder="$t('method.Mslb.dialog.min_ds_limit_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.max_ds_limit')">
          <el-input v-model="partner.ds_max" :placeholder="$t('method.Mslb.dialog.max_ds_limit_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.superior_id')">
          <el-input v-model="partner.pid" :placeholder="$t('method.Mslb.dialog.superior_id_placeholder')" :disabled="dialogType === 'edit'" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.vip_level')">
          <el-input-number v-model="partner.vip" :placeholder="$t('method.Mslb.dialog.vip_level_placeholder')" :integer="true" :min="1" :max="13" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.internal_partner')">
          <el-switch v-model="partner.type" :active-value="0" :inactive-value="1" active-color="#13ce66" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.banned')">
          <el-switch v-model="partner.banned" :active-value="1" :inactive-value="0" active-color="#13ce66" />
        </el-form-item>
        <el-form-item v-show="partner.type === 0" :label="$t('method.Mslb.dialog.hash_login')">
          <el-input v-model="partner.hash_login" :placeholder="$t('method.Mslb.dialog.hash_login')" />
        </el-form-item>
        <el-form-item v-show="partner.type === 0" :label="$t('method.Mslb.dialog.hash_trade')">
          <el-input v-model="partner.hash_trade" :placeholder="$t('method.Mslb.dialog.hash_trade')" />
        </el-form-item>
        <el-form-item v-if="dialogType === 'edit'" :label="$t('method.Mslb.dialog.change_type')" style="max-width: 282px;">
          <el-select v-model="changeBalance.changeBalanceType" clearable :placeholder="$t('method.Mslb.dialog.change_type_placeholder')">
            <el-option
              v-for="item in balanceType"
              :key="item.name"
              :label="item.label"
              :value="item.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item
          v-if="changeBalance.changeBalanceType && dialogType === 'edit'"
          :label="$t('method.Mslb.dialog.change_amount')"
          style="max-width: 282px;"
        >
          <el-input v-model="changeBalance.changeAmount" :placeholder="$t('method.Mslb.dialog.change_amount_placeholder')" />
          <span style="color: red;">{{ $t('method.Mslb.dialog.change_amount_warning') }}</span>
        </el-form-item>
        <el-form-item
          v-if="changeBalance.changeBalanceType && dialogType === 'edit'"
          :label="$t('method.Mslb.dialog.remark')"
          style="max-width: 282px;"
        >
          <el-input v-model="changeBalance.remark" :placeholder="$t('method.Mslb.dialog.remark_placeholder')" />
        </el-form-item>
      </el-form>

      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('method.Mslb.buttons.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('method.Mslb.buttons.confirm') }}</el-button>
      </div>
    </el-dialog>
    <el-dialog :visible.sync="dialogVisibleMigrate" :title="$t('method.Mslb.dialog.permissions')" :close-on-click-modal="false">
      <el-form :model="partner" label-width="115px" label-position="left">
        <el-form-item :label="$t('method.Mslb.dialog.current_partner_id')">
          <el-input v-model="partner.id" :disabled="true" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.superior_partner_id')">
          <el-input v-model="partner.pid" :disabled="true" />
        </el-form-item>
        <el-form-item :label="$t('method.Mslb.dialog.migrate_partner_id')">
          <el-input v-model="partner.migrationId" :placeholder="$t('method.Mslb.dialog.migrate_partner_id_placeholder')" />
        </el-form-item>
      </el-form>
      <el-checkbox v-model="expandAll" :label="$t('method.Mslb.dialog.expand_all')" @change="expandAllClick"></el-checkbox>
      <el-tree
        ref="tree"
        :data="routesData"
        :props="defaultProps"
        :default-expand-all="expandAll"
        :empty-text="$t('noData')"
        accordion
      ></el-tree>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisibleMigrate=false">{{ $t('method.Mslb.buttons.cancel') }}</el-button>
        <el-button type="danger" @click="confirmMigration">{{ $t('method.Mslb.buttons.confirm') }}</el-button>
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
    getPartner,
    addPartner,
    exportPartner,
    updatePartner,
    updatePartnerUnlock,
    updatePartnerLock, getMigrate, migratePartner, handleClearBalance
} from '@/api/partner'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
import { isValidPartnerPayPassword } from '@/utils/partnerPassword'

export default {
    name: 'Mslb',
    data() {
        return {
            ids: [], //ids
            columnList: [
              { name: this.$t('method.Mslb.table.balance'), key: 'balance' },
              { name: this.$t('method.Mslb.table.frozen_balance'), key: 'balance_frozen' },
              { name: this.$t('method.Mslb.table.deposit'), key: 'balance_deposit' },
            ],
            new_partner: 0,
            online_partner: 0,
            online_ds_partner: 0,
            online_df_partner: 0,
            partner: {},
            partnerList: [],
            dialogVisible: false,
            dialogType: 'new',
            changeBalance: {},
            balanceType: [
        { name: 'balance', label: this.$t('method.Mslb.balanceType.balance') },
        { name: 'balance_frozen', label: this.$t('method.Mslb.balanceType.balance_frozen') },
        { name: 'balance_deposit', label: this.$t('method.Mslb.balanceType.balance_deposit') }
      ],
      formItemList: [
        { label: this.$t('method.Mslb.formItemList.id'), type: 'input', param: 'id' },
        { label: this.$t('method.Mslb.formItemList.cellphone'), type: 'input', param: 'cellphone' },
        { label: this.$t('method.Mslb.formItemList.name'), type: 'input', param: 'name' },
        { label: this.$t('method.Mslb.formItemList.pid'), type: 'input', param: 'pid' },
        { label: this.$t('method.Mslb.formItemList.status'), type: 'select', selectOptions: [{ value: 0, label: '锁定' }, { value: 1, label: '正常' }], param: 'status' },
        { label: this.$t('method.Mslb.formItemList.certified'), type: 'select', selectOptions: [{ value: 0, label: '未认证' }, { value: 1, label: '已认证' }], param: 'certified' },
        { label: this.$t('method.Mslb.formItemList.type'), type: 'select', selectOptions: [{ value: 0, label: '内部' }, { value: 1, label: '外部' }], param: 'type' },
        { label: this.$t('method.Mslb.formItemList.time_create'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' },
        { label: this.$t('method.Mslb.formItemList.top_partner_id'), type: 'input', param: 'top_partner_id' },
        { label: this.$t('method.Mslb.formItemList.online'), type: 'select', selectOptions: [{ value: 0, label: '全部' }, { value: 1, label: '代收' }, { value: 2, label: '代付' }], param: 'online' },
        { label: this.$t('method.Mslb.formItemList.time_accept'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_accept' },

        {
            label: this.$t('method.df.form.balance_range'),
            type: 'input',
            param: 'amount_range_new'
        },
      ],
      exportData: {
        tHeader: [
          this.$t('method.Mslb.exportData.id'),
          this.$t('method.Mslb.exportData.cellphone'),
          this.$t('method.Mslb.exportData.name'),
          this.$t('method.Mslb.exportData.pid'),
          this.$t('method.Mslb.exportData.vip'),
          this.$t('method.Mslb.exportData.balance'),
          this.$t('method.Mslb.exportData.balance_frozen'),
          this.$t('method.Mslb.exportData.status'),
          this.$t('method.Mslb.exportData.type'),
          this.$t('method.Mslb.exportData.time_create'),
          this.$t('method.Mslb.exportData.balance_deposit'),
          this.$t('method.Mslb.exportData.ds_min'),
          this.$t('method.Mslb.exportData.ds_max'),
          this.$t('method.Mslb.exportData.invitation_code')
        ],
        filterVal: ['id', 'cellphone', 'name', 'pid', 'vip', 'balance', 'balance_frozen', 'certified', 'type', 'time_create', 'balance_deposit', 'ds_min', 'ds_max', 'invitation_code'],
        list: [],
        filename: this.$t('method.Mslb.exportData.filename')
      },
            params: {},
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            },
            dialogVisibleMigrate: false,
            expandAll: false,
            defaultProps: {
                children: 'children',
                label: 'label'
            },

            routesData: []
        }
    },
    created() {
        this.getData()
    },
    methods: {
          /* 排序*/
          async sort_change({ column }) {
              this.order_field = this.columnList.find(item => item.name === column.label).key
              if (column.order === 'ascending') {
                  this.sort = 'asc'
              } else if (column.order === 'descending') {
                  this.sort = 'desc'
              } else {
                  this.order_field = 'id'
                  this.sort = 'desc'
              }
              this.getData()
          },
          /* 清空余额 */
          async handleClearBalance() {
              if (this.ids.length == 0) {
                  this.$message({
                      type: 'error',
                      message: this.$t('method.no_data_selected')
                  })
                  return
              }
              this.$confirm(this.$t('method.clear_balance.confirm'), this.$t('method.clear_balance.title'), {
                  type: 'warning',
                  confirmButtonText: this.$t('method.confirm'),
                  cancelButtonText: this.$t('method.cancel'),
              }).then(async () => {
                  try {
                      await handleClearBalance({ id: this.ids });
                  } catch (err) {
                      return;
                  }
                  this.$message({
                      type: 'success',
                      message: this.$t('method.update_success')
                  });
                  this.getData();
              }).catch(() => {
                  // this.$message({
                  //     type: 'info',
                  //     message: this.$t('method.action_cancelled')
                  // });
              });


          },
          // 表格勾选
          async selectionChangeHandlerOrder(val) {
              var _this = this
              this.ids = []
              if (val.length !== 0) {
                  val.forEach(function(item) {
                      _this.ids.push(item.id)
                  });
              } else {
                  this.ids = []
              }

              // console.log(111, val, this.orderCode)
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
            data.order_field = this.order_field
            data.sort = this.sort
            if (isExport) {
                data.size = 0
                data.page = 0
            } else {
                data.size = this.paginationData.size
                data.page = this.paginationData.page
            }
            // 去掉首尾空格
            // const input = this.params.amount_range_new.trim();
            const input = (this.params.amount_range_new || '').trim();
            // 空值逻辑
            if (input) {
                // 检查格式是否符合 "数字-数字"
                if (!/^\d+-\d+$/.test(input)) {
                  this.$message({
                    type: 'warning',
                    message: '输入格式不正确，请使用类似 11-22 的格式',
                  });
                  return;
                }

                // 分割成两个数字
                const [min, max] = input.split('-').map(Number);

                // 检查两个数字是否有效
                if (min <= 0 || max <= 0) {
                  this.$message({
                    type: 'warning',
                    message: '金额必须大于 0',
                  });
                  return;
                }

                if (min >= max) {
                  this.$message({
                    type: 'warning',
                    message: '范围的后一个数字必须大于前一个数字',
                  });
                  return;
                }
            }
            if (isExport) {
              const res = await exportPartner(data)
              this.$message({
                type: 'success',
                message: this.$t('search.exportMessage')
              })
              this.paginationData.total = res.total
              this.exportData.list = res.data
              this.$refs.search.exportExcel()
            } else {
                const res = await getPartner(data)
                this.partnerList = res.data
                this.paginationData.total = res.total
                this.new_partner = res.new_partner
                this.online_partner = res.online_partner
                this.online_ds_partner = res.online_ds_partner
                this.online_df_partner = res.online_df_partner
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
        /* 新增成员*/
        handleAdd() {
            this.dialogType = 'new'
            this.dialogVisible = true
            this.partner = {}
        },
        /* 编辑码商*/
        handleEdit(scope) {
            this.dialogType = 'edit'
            this.dialogVisible = true
            this.partner = deepClone(scope.row)
            this.changeBalance = {}
        },
        /* 迁移码商*/
        async migrateEdit(scope) {
            const res = await getMigrate(scope.row)
            this.dialogVisibleMigrate = true
            this.routesData = res.data
            this.partner = deepClone(scope.row)
        },
        async expandAllClick(val) {
            this.expandAll = val
            this.changeTreeNodeStatus(this.$refs.tree.store.root)
        },
        async changeTreeNodeStatus(node) {
            node.expanded = this.expandAll
            for (var i = 0; i < node.childNodes.length; i++) {
                //改变节点自身的expanded状态
                node.childNodes[i].expanded = this.expandAll;
                //遍历子节点
                if (node.childNodes[i].childNodes.length > 0) {
                    this.changeTreeNodeStatus(node.childNodes[i])
                }
            }
        },
        async confirmMigration() {
            var data = {}
            data.migrationId = this.partner.migrationId
            data.id = this.partner.id
            try {
                await migratePartner(data)
            } catch (err) {
                return
            }
            this.dialogVisibleMigrate = false
            this.$notify({
                title: this.$t('method.migration_success'),
                dangerouslyUseHTMLString: true,
                message: `
            <div>ID: ${data.id}</div>
          `,
                type: 'success'
            })
            this.getData()
            this.dialogVisibleMigrate = false
            this.getData()
        },
        /* 改变状态*/
    async changeStatus({ $index, row }, type) {
        const tipsString = row.status === 1 ? this.$t('method.lock') : this.$t('method.unlock')
        this.$confirm(this.$t('method.confirm_action', { action: tipsString }), this.$t('method.warning'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async() => {
            var data = {}
            data.id = row.id
            data.status = row.status === 1 ? 0 : 1
            try {
                row.status === 1 ? await updatePartnerLock(data) : await updatePartnerUnlock(data)
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
    /* 确认编辑 */
    async confirmRole() {
        var data = {}
        data.id = this.partner.id
        data.cellphone = this.partner.cellphone
        data.name = this.partner.name
        data.ds_min = this.partner.ds_min
        data.ds_max = this.partner.ds_max
        data.pid = this.partner.pid
        data.rate_df = this.partner.rate_df
        data.type = this.partner.type
        data.vip = this.partner.vip
        data.banned = this.partner.banned
        data.hash_login = this.partner.hash_login
        data.hash_trade = this.partner.hash_trade
        if (this.dialogType === 'edit') {
                if (this.changeBalance && this.changeBalance.changeBalanceType && this.changeBalance
                    .changeAmount && this.changeBalance.remark) {
                if (this.changeBalance.remark) {
                    data.changeBalance = this.changeBalance
                } else {
                    this.$message({
                        type: 'warning',
                        message: this.$t('method.fill_remark')
                    })
                    return
                }

            } else {
              if (this.partner.type === 0) {
                  const passwordPattern = /^(?=.*[a-zA-Z])(?=.*\d)(?=.*[!@#$%^&*()_+={}\[\]:;'",<>\./?\\|]).{8,20}$/;

                  // 如果 hash_login 不为空并且不是加密字符串，进行验证
                  if (this.partner.hash_login && !passwordPattern.test(this.partner.hash_login)) {
                    // this.passwordError = 'hash_login 必须包含字母、数字和特殊字符，并且长度在 8 到 20 位之间';
                    this.$message({
                        type: 'warning',
                        message: this.$t('method.login_password_msg')
                    })
                    return;
                  }

                  if (!isValidPartnerPayPassword(this.partner.hash_trade)) {
                    this.$message({
                        type: 'warning',
                        message: this.$t('method.pay_password_msg')
                    })
                    return;
                  }
                }
            }
            try {
                await updatePartner(data)
            } catch (err) {
                return
            }
        } else {
            try {
                await addPartner(data)
            } catch (err) {
                return
            }
        }
            const {
                id,
                name
            } = this.partner
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
    },
    // 显示特定颜色等样式
    cellStyle({ row, column, rowIndex, columnIndex }) {
        if (row.type === 0 && column.label === this.$t('method.partner_type')) {
            return 'color: #fd5757;font-size:125%;'
        }
        const { id, name } = this.partner
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
    },
    // 显示特定颜色等样式
    cellStyle({ row, column, rowIndex, columnIndex }) {
        if (row.type === 0 && column.label === this.$t('method.partner_type')) {
            return 'color: #fd5757;font-size:125%;'
        }
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
