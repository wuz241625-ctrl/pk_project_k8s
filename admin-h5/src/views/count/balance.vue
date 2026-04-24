<template>
  <div class="app-container">
    <el-form>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance)">{{ $t('shmsye.total') }}：{{ nowBalance.balance }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_m)">{{ $t('shmsye.merchant') }}：{{ nowBalance.balance_m }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_m_frozen)">{{ $t('shmsye.merchantFrozen') }}：{{ nowBalance.balance_m_frozen }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p)">{{ $t('shmsye.partner') }}：{{ nowBalance.balance_p }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p_frozen)">{{ $t('shmsye.partnerFrozen') }}：{{ nowBalance.balance_p_frozen }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p_deposit)">{{ $t('shmsye.partnerDeposit') }}：{{ nowBalance.balance_p_deposit }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p_inside)">{{ $t('shmsye.insidePartner') }}：{{ nowBalance.balance_p_inside }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p_frozen_inside)">{{ $t('shmsye.insidePartnerFrozen') }}：{{ nowBalance.balance_p_frozen_inside }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p_outside)">{{ $t('shmsye.outsidePartner') }}：{{ nowBalance.balance_p_outside }}</el-button>
      <el-button type="primary" plain @click="handlecopy(nowBalance.balance_p_frozen_outside)">{{ $t('shmsye.outsidePartnerFrozen') }}：{{ nowBalance.balance_p_frozen_outside }}</el-button>
    </el-form>
    <el-button type="primary" :disabled="isQueryDisabled" @click="refreshBalance">{{ $t('route.refreshBalance') }}</el-button>
    <el-table :data="balanceList" stripe style="width: 100%;margin-top:30px;" border :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('shmsye.time')">
        <template slot-scope="scope">
          {{ scope.row.created }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.total')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.merchant')">
        <template slot-scope="scope">
          {{ scope.row.balance_m }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.merchantFrozen')">
        <template slot-scope="scope">
          {{ scope.row.balance_m_frozen }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.partner')">
        <template slot-scope="scope">
          {{ scope.row.balance_p }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.partnerFrozen')">
        <template slot-scope="scope">
          {{ scope.row.balance_p_frozen }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.partnerDeposit')">
        <template slot-scope="scope">
          {{ scope.row.balance_p_deposit }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.insidePartner')">
        <template slot-scope="scope">
          {{ scope.row.balance_p_inside }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.insidePartnerFrozen')">
        <template slot-scope="scope">
          {{ scope.row.balance_p_frozen_inside }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.outsidePartner')">
        <template slot-scope="scope">
          {{ scope.row.balance_p_outside }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('shmsye.outsidePartnerFrozen')">
        <template slot-scope="scope">
          {{ scope.row.balance_p_frozen_outside }}
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
import { getBalance } from '@/api/count'

export default {
    data() {
        return {
            balanceList: [],
            nowBalance: {},
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            },
            isQueryDisabled: false
        }
    },
    created() {
        this.getData()
    },
    methods: {
    /* 获取数据 */
        async getData() {
            var data = {}
            data.size = this.paginationData.size
            data.page = this.paginationData.page
            const res = await getBalance(data)
            this.balanceList = res.data
            this.count = res.count
            this.paginationData.total = res.total
            this.nowBalance = res.count
        },
        /* 点击复制 */
        handlecopy(amount) {
            const oInput = document.createElement('input')
            oInput.value = amount
            document.body.appendChild(oInput)
            oInput.select() // 选择对象;
            document.execCommand('Copy') // 执行浏览器复制命令
            this.$notify({
                title: this.$t('method.copySuccess'),
                type: 'success'
            })
        },
        refreshBalance() {
            this.getData()
            // 限制点击
            this.isQueryDisabled = true
            setTimeout(() => {
                this.isQueryDisabled = false
            }, 5000)
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
<style lang="scss" scoped>
  .el-button{
    margin: 3px;
  }
</style>

