<template>
  <div class="app-container">
    <el-button type="primary" @click="getData">{{ $t('dsdfpz.buttons.search') }}</el-button>
    <el-button type="primary" @click="handleAdd">{{ $t('dsdfpz.buttons.add') }}</el-button>
    <el-table :data="channelList" style="width: 100%;margin-top:30px;" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">
      <el-table-column align="center" :label="$t('dsdfpz.columns.id')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.merchant_id')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.merchant_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.key')">
        <template slot-scope="scope">
          {{ scope.row.key }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.key2')">
        <template slot-scope="scope">
          {{ scope.row.key2 }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.key3')">
        <template slot-scope="scope">
          {{ scope.row.key3 }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.name')">
        <template slot-scope="scope">
          {{ scope.row.name }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.pay_url')">
        <template slot-scope="scope">
          {{ scope.row.pay_url }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.channel_code')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.channel_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.notify_ip')">
        <template slot-scope="scope">
          {{ scope.row.notify_ip }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.query_url')">
        <template slot-scope="scope">
          {{ scope.row.query_url }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.forcible')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.forcible === 1 ? $t('dsdfpz.options.yes') : $t('dsdfpz.options.no') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.status')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.status === 1 ? $t('dsdfpz.options.normal') : $t('dsdfpz.options.disable') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.updated')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.updated }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.created')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.created }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.operation')" width="150px">
        <template slot-scope="scope">
          <el-button type="success" size="small" @click="handleEdt(scope)">{{ $t('dsdfpz.buttons.edt') }}</el-button>
          <el-button type="danger" size="small" @click="handleDel(scope)">{{ $t('dsdfpz.buttons.del') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="(dialogType === 'add' ? $t('dsdfpz.diglogs.add') : $t('dsdfpz.diglogs.edt')) + ' ' + $t('routes.systemSettings.channel.titleds')" :close-on-click-modal="false">
      <el-form :model="settings" label-width="120px" label-position="left">
        <el-form-item :label="$t('dsdfpz.columns.id')" style="display: none"><el-input v-model="settings.merchant_id" /></el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.merchant_id')">
          <el-input v-model="settings.merchant_id" :placeholder="$t('dsdfpz.tips.merchant_id')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.key')">
          <el-input v-model="settings.key" :placeholder="$t('dsdfpz.tips.key')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.key2')">
          <el-input v-model="settings.key2" :placeholder="$t('dsdfpz.tips.key2')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.key3')">
          <el-input v-model="settings.key3" :placeholder="$t('dsdfpz.tips.key3')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.name')">
          <el-input v-model="settings.name" :placeholder="$t('dsdfpz.tips.name')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.pay_url')">
          <el-input v-model="settings.pay_url" :placeholder="$t('dsdfpz.tips.pay_url')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.channel_code')">
          <el-input v-model="settings.channel_code" :placeholder="$t('dsdfpz.tips.channel_code')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.notify_ip')">
          <el-input v-model="settings.notify_ip" :placeholder="$t('dsdfpz.tips.notify_ip')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.query_url')">
          <el-input v-model="settings.query_url" :placeholder="$t('dsdfpz.tips.query_url')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.forcible')">
          <el-select v-model="settings.forcible" :placeholder="$t('dsdfpz.tips.forcible')">
            <el-option :value="1" :label="$t('dsdfpz.options.yes')"></el-option>
            <el-option :value="0" :label="$t('dsdfpz.options.no')"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.status')">
          <el-select v-model="settings.status" :placeholder="$t('dsdfpz.tips.status')">
            <el-option :value="1" :label="$t('dsdfpz.options.normal')"></el-option>
            <el-option :value="0" :label="$t('dsdfpz.options.disable')"></el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('dsdfpz.buttons.cancel') }}</el-button>
        <el-button type="success" @click="handleSave">{{ $t('dsdfpz.buttons.confirm') }}</el-button>
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
import { deepClone } from '@/utils'
import { addDSSettings, delDSSettings, edtDSSettings, getDSSettings } from '@/api/setting'

const defaultSettings = {
    id: '',
    merchant_id: '',
    key: '',
    key2: '',
    key3: '',
    name: '',
    pay_url: '',
    channel_code: null,
    notify_ip: '',
    query_url: '',
    forcible: 1,
    status: 1,
}

export default {
    data() {
        return {
            dialogVisible: false,
            settings: Object.assign({}, defaultSettings),
            channelList: [],
            paginationData: {
                page: 1,
                size: 10,
                total: 200
            },
            dialogType: ""
        }
    },
    created() {
        this.getData()
    },
    methods: {
        /* 改变分页大小 */
        handleSizeChange(val) {
            this.paginationData.size = val;
            this.getData();
        },

        /* 改变当前页 */
        handleCurrentChange(val) {
            this.paginationData.page = val;
            this.getData();
        },

        /* 获取数据 */
        async getData() {
            const data = { 'size': this.paginationData.size, 'page': this.paginationData.page };
            var res = await getDSSettings(data);
            this.channelList = res.data;
            this.paginationData.total = res.total;
        },

        handleDel({ $index, row }) {
            this.$confirm(this.$t('dsdfpz.diglogs.confirmdel'), this.$t('routes.systemSettings.channel.titleds'), {
                type: 'warning',
                confirmButtonText: this.$t('dsdfpz.buttons.confirm'),
                cancelButtonText: this.$t('dsdfpz.buttons.cancel')
            }).then(async () => {
                try { await delDSSettings({ 'id': row.id }) } catch (err) { return }
                this.$message({
                    type: 'success',
                    message: this.$t('dsdfpz.alerts.successdel')
                });
                this.getData();
            }).catch(() => {});
        },

        handleAdd() {
            this.dialogType = 'add'
            this.dialogVisible = true
            this.settings = Object.assign({}, defaultSettings);
        },

        handleEdt(scope) {
            this.dialogType = 'edt'
            this.dialogVisible = true;
            this.settings = deepClone(scope.row);
        },

        async handleSave() {
            var res;
            try {
                if(this.settings.id === null || this.settings.id === '')
                    res = await addDSSettings(this.settings);
                else
                    res = await edtDSSettings(this.settings);

                if(res.code != "20000") {
                    this.$message({
                        type: 'warning',
                        message: this.$t('dsdfpz.alerts.fail')
                    })
                    return;
                }
            } catch (err) {
                return;
            }

            this.dialogVisible = false;
            this.$notify({
                type: 'success',
                title: this.$t('method.save.successTitle'),
                dangerouslyUseHTMLString: true,
                message: `
                    <div>${this.$t('dsdfpz.alerts.success')}</div>
                `
            });
            this.getData();
        },
  }
}
</script>
