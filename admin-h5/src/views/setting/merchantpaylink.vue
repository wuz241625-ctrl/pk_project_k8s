<template>
  <div class="app-container">
    <el-button type="primary" @click="handleAdd">{{ $t('merchantpaylink.addLink') }}</el-button>
    <el-table
      :data="merchantpaylinklist"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('merchantpaylink.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchantpaylink.table.payName')">
        <template slot-scope="scope">
          {{ scope.row.pay_name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchantpaylink.table.payLink')">
        <template slot-scope="scope">
          {{ scope.row.pay_link }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('merchantpaylink.table.operation')">
        <template slot-scope="scope">
          <el-button @click="handleEdit(scope)">{{ $t('message.button.edit') }}</el-button>
          <el-button type="danger" @click="handleDelete(scope.row.id)">{{ $t('message.button.delete') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="dialogTitle" :close-on-click-modal="false">
      <el-form :model="linkData" label-width="80px" label-position="left">
        <el-form-item :label="$t('merchantpaylink.dialog.payName')" label-width="120px">
          <el-input v-model="linkData.pay_name" :placeholder="$t('merchantpaylink.dialog.placeholderPayName')" />
        </el-form-item>
        <el-form-item :label="$t('merchantpaylink.dialog.payLink')" label-width="120px">
          <el-input v-model="linkData.pay_link" :placeholder="$t('merchantpaylink.dialog.placeholderPayLink')" />
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('merchantpaylink.dialog.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('merchantpaylink.dialog.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { deepClone } from '@/utils'
import { getMerchantPayLink, addMerchantPayLink, editMerchantPayLink, delMerchantPayLink } from '@/api/setting'

export default {
  data() {
    return {
      dialogVisible: false,
      merchantpaylinklist: [],
      linkData: {},
      dialog_type: 'add',
      dialogTitle : ''
    }
  },
  created() {
    this.getData()
  },
  methods: {
    // 获取设置
    async getData() {
      const res = await getMerchantPayLink()
      this.merchantpaylinklist = res.data
    },
    /* 新增链接*/
    handleAdd() {
      this.dialogVisible = true
      this.dialog_type = 'add'
      this.linkData = {}, // 重置数据
      this.dialogTitle = this.$t('merchantpaylink.dialog.addTitle')
    },
    /* 编辑链接*/
    handleEdit(scope) {
      this.dialogVisible = true
      this.dialog_type = 'edit'
      this.linkData = deepClone(scope.row)
      this.dialogTitle = this.$t('merchantpaylink.dialog.editTitle')
    },
    /* 删除链接*/
    async handleDelete(id) {
      this.$confirm(this.$t('method.confirm_delete'), this.$t('method.prompt'), {
        confirmButtonText: this.$t('method.confirm'),
        cancelButtonText: this.$t('method.cancel'),
        type: 'warning'
      }).then(async () => {
        await delMerchantPayLink({ id })
        this.$notify({
          title: this.$t('method.delete_success'),
          type: 'success'
        })
        this.getData() // 重新获取数据
      }).catch(() => {});
    },
    /* 确认保存*/
    async confirmRole() {
      var data = this.linkData
      if (this.dialog_type === 'add') {
        try {
          await addMerchantPayLink(data)
        } catch (err) {
          return
        }
      } else {
        try {
          await editMerchantPayLink(data)
        } catch (err) {
          return
        }
      }
      this.dialogVisible = false
      this.$notify({
        title: this.$t('method.save_success'),
        type: 'success'
      })
      this.getData()
    }
  }
}
</script>

<style lang="scss" scoped>
.app-container {
  .confButton {
    margin-left: 100px;
  }
}
</style>
