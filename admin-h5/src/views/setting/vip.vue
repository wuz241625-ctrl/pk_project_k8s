<template>
  <div class="app-container">
    <el-table
      :data="viplist"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('Vip.table.vipLevel')">
        <template slot-scope="scope">
          {{ 'VIP' + scope.row.vip }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.balanceLimit')">
        <template slot-scope="scope">
          {{ scope.row.conditions }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.dsMin')">
        <template slot-scope="scope">
          {{ scope.row.ds_min }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.dsMax')">
        <template slot-scope="scope">
          {{ scope.row.ds_max }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.dfMin')">
        <template slot-scope="scope">
          {{ scope.row.df_min }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.dfMax')">
        <template slot-scope="scope">
          {{ scope.row.df_max }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.topCard')" width="120px">
        <template slot-scope="scope">
          {{ scope.row.top_card }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.depositRatio')" width="120px">
        <template slot-scope="scope">
          {{ scope.row.deposit_ratio }}%
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('Vip.table.action')" width="120px">
        <template slot-scope="scope">
          <el-button type="primary" size="small" @click="handleEdit(scope)">{{ $t('Vip.table.edit') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="$t('Vip.dialog.editTitle')" :close-on-click-modal="false">
      <el-form :model="vip" label-width="80px" label-position="left">
        <el-form-item :label="$t('Vip.dialog.vipLevel')" label-width="120px">
          <el-input v-model="vip.vip" :disabled="true" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.balanceLimit')" label-width="120px">
          <el-input v-model="vip.conditions" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.dsMin')" label-width="120px">
          <el-input v-model="vip.ds_min" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.dsMax')" label-width="120px">
          <el-input v-model="vip.ds_max" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.dfMin')" label-width="120px">
          <el-input v-model="vip.df_min" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.dfMax')" label-width="120px">
          <el-input v-model="vip.df_max" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.topCard')" label-width="120px">
          <el-input v-model="vip.top_card" :placeholder="$t('Vip.dialog.placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('Vip.dialog.depositRatio')" label-width="120px">
          <el-input v-model="vip.deposit_ratio" :placeholder="$t('Vip.dialog.placeholder')" style="width: 10%;" />%  
          <el-span style="color: red;">{{ $t('Vip.dialog.depositTip') }}</el-span>
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('Vip.dialog.cancel') }}</el-button>
        <el-button type="danger" @click="confirmRole">{{ $t('Vip.dialog.confirm') }}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { deepClone } from '@/utils'
import { getVip, updateVip } from '@/api/setting'
export default {
    data() {
        return {
            dialogVisible: false,
            viplist: [],
            vip: {}
        }
    },
    created() {
        this.getData()
    },
    methods: {
        // 获取设置
        async getData() {
            const res = await getVip()
            this.viplist = res.data
        },
        /* 编辑通道*/
        handleEdit(scope) {
            this.dialogVisible = true
            this.vip = deepClone(scope.row)
        },
        /* 确认保存*/
        async confirmRole() {
            var data = this.vip
            try { await updateVip(data) } catch (err) { return }
            const { vip } = this.vip
            this.dialogVisible = false
            this.$notify({
                title: this.$t('method.save_success'),
                dangerouslyUseHTMLString: true,
                message: `
            		<div>VIP: ${vip}</div>
            	`,
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
