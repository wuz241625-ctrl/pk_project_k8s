<template>
  <div class="app-container">
    <baseSearch :form-item-list="formItemList" @search="getData" :placeholder="$t('method.Yjgl.form.placeholderSearch')" />
    <el-button type="primary" @click="handleAdd">{{ $t('method.Yjgl.form.add') }}</el-button>
    <el-table
      :data="phone_list"
      style="width: 100%; margin-top: 30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('method.Yjgl.form.phoneId')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yjgl.form.password')">
        <template slot-scope="scope">
          {{ scope.row.pw }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yjgl.form.codeId')">
        <template slot-scope="scope">
          {{ scope.row.payment_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yjgl.form.connectionStatus')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.online_ds === 1 ? 'success' : 'danger'">
            {{ scope.row.callback === 1 ? $t('method.Yjgl.form.connected') : $t('method.Yjgl.form.notConnected') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.Yjgl.form.creationTime')">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" align="center" :label="$t('method.Yjgl.form.operation')">
        <template slot-scope="scope">
          <el-button v-if="scope.row.occupied === 1" type="warning" size="mini" @click="handleUpdate(scope, 0)">
            {{ $t('method.Yjgl.form.reset') }}
          </el-button>
          <el-button type="warning" size="mini" @click="handleUpdate(scope, 1)">
            {{ $t('method.Yjgl.form.changePassword') }}
          </el-button>
          <el-button type="danger" size="mini" @click="handleDelete(scope)">
            {{ $t('method.Yjgl.form.delete') }}
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
  </div>
</template>

<script>
import { get_phonepe, add_phonepe, update_phonepe, del_phonepe } from '@/api/partner'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Yjgl',
    data() {
        return {
            phone_list: [],
            params: {},
            formItemList: [ // 搜索栏设置
        {
          label: this.$t('method.Yjgl.ds.form.id'),
          type: 'input',
          param: 'id'
        },
        {
          label: this.$t('method.Yjgl.ds.form.payment_id'),
          type: 'input',
          param: 'payment_id'
        },
        {
          label: this.$t('method.Yjgl.ds.form.status'),
          type: 'select',
          param: 'status',
          selectOptions: [
            {
              value: 0,
              label: this.$t('method.Yjgl.ds.status_selectOptions.0')
            },
            {
              value: 1,
              label: this.$t('method.Yjgl.ds.status_selectOptions.1')
            }
          ]
        },
        {
          label: this.$t('method.Yjgl.ds.form.time_create'),
          type: 'dateTimePicker',
          pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
          param: 'time_create'
        }
      ],
            paginationData: { page: 1, size: 10, total: 200 }
        }
    },
    created() { this.getData() },
    methods: {
        /* 获取数据*/
        async getData(params) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
            }
            var data = {}
            data.serchData = this.params
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            const res = await get_phonepe(data)
            this.phone_list = res.data
            this.paginationData.total = res.total
        },
        /* 新增云集*/
    handleAdd() {
        this.$prompt(this.$t('method.add_prompt.placeholder'), this.$t('method.add_prompt.title'), { type: 'warning',
              confirmButtonText: this.$t('method.confirm'),
              cancelButtonText: this.$t('method.cancel') })
            .then(async({ value }) => {
                try { await add_phonepe({ id: value }) } catch (err) { return }
                this.$message({ type: 'success', message: this.$t('method.add_prompt.success') })
                this.getData()
            }).catch(() => {})
    },
        /* 重置云机*/
    handleUpdate({ $index, row }, type) {
        if (type === 1) {
            this.$prompt(this.$t('method.update_password.placeholder'), this.$t('method.update_password.title'), { type: 'warning',
                        confirmButtonText: this.$t('method.confirm'),
                        cancelButtonText: this.$t('method.cancel') })
                .then(async({ value }) => {
                    try { await update_phonepe({ id: row.id, pw: value }) } catch (err) { return }
                    this.$message({ type: 'success', message: this.$t('method.update_password.success') })
                    this.getData()
                }).catch(() => {})
        } else if (type === 0) {
            this.$confirm(this.$t('method.reset_prompt.confirm'), this.$t('method.reset_prompt.title'), { type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel') })
                .then(async() => {
                    try { await update_phonepe({ id: row.id }) } catch (err) { return }
                    this.$message({ type: 'success', message: this.$t('method.reset_prompt.success') })
                    this.getData()
                }).catch(() => {})
        }
    },
        /* 删除云机*/
    handleDelete({ $index, row }) {
        this.$confirm(this.$t('method.delete_prompt.confirm'), this.$t('method.delete_prompt.title'), { type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel') })
            .then(async() => {
                try { await del_phonepe({ id: row.id }) } catch (err) { return }
                this.$message({ type: 'success', message: this.$t('method.delete_prompt.success') })
                this.getData()
            }).catch(() => {})
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
        }
    }
}
</script>
