<template>
  <div class="app-container">
    <el-button type="primary">{{ $t('channel.totalCount') + channelList.length }}</el-button>
    <el-table
      :data="channelList"
      style="width: 100%;margin-top:30px;"
      border
      stripe
      :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
    >
      <el-table-column align="center" :label="$t('channel.table.code')">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('channel.table.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('channel.table.rate')">
        <template slot-scope="scope">
          {{ scope.row.rate }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('channel.table.limit')">
        <template slot-scope="scope">
          {{ scope.row.fixed === 1 ? scope.row.amount_fixed : parseInt(scope.row.amount_min) + '~' + parseInt(scope.row.amount_max) }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('channel.table.status')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.status === 1 ? 'success' : 'warning'">
            {{ scope.row.status === 1 ? $t('channel.table.statusOpen') : $t('channel.table.statusMaintaining') }}
          </el-tag>
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
import {
    getChannel
} from '@/api/setting'

export default {
    data() {
        return {
            channelList: [],
            dialogVisible: false,
            dialogVisibleTest: false,
            paginationData: {
                page: 1,
                size: 10,
                total: 0
            }
        }
    },
    created() {
        this.getData()
    },
    methods: {
        /* 获取数据*/
        async getData() {
            var data = {
                'size': this.paginationData.size,
                'page': this.paginationData.page
            }
            var res = await getChannel(data)
            this.channelList = res.data
            this.paginationData.total = res.total
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
