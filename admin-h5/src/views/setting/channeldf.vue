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
      <el-table-column align="center" :label="$t('dsdfpz.columns.mer_id')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.mer_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.mer_key')">
        <template slot-scope="scope">
          {{ scope.row.mer_key }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.mer_key2')">
        <template slot-scope="scope">
          {{ scope.row.mer_key2 }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.mer_key3')">
        <template slot-scope="scope">
          {{ scope.row.mer_key3 }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.mer_key4')">
        <template slot-scope="scope">
          {{ scope.row.mer_key4 }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.pay_name_zh')">
        <template slot-scope="scope">
          {{ scope.row.pay_name_zh }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.pay_name')">
        <template slot-scope="scope">
          {{ scope.row.pay_name }}
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
      <el-table-column align="center" :label="$t('dsdfpz.columns.is_self')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.is_self === 1 ? $t('dsdfpz.options.yes') : $t('dsdfpz.options.no') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.is_xiaoshu')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.is_xiaoshu === 1 ? $t('dsdfpz.options.yes') : $t('dsdfpz.options.no') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.status')" width="100px">
        <template slot-scope="scope">
          {{ scope.row.status === 1 ? $t('dsdfpz.options.normal') : $t('dsdfpz.options.disable') }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('dsdfpz.columns.operation')" width="150px">
        <template slot-scope="scope">
          <el-button type="success" size="small" @click="handleEdt(scope)">{{ $t('dsdfpz.buttons.edt') }}</el-button>
          <el-button type="danger" size="small" @click="handleDel(scope)">{{ $t('dsdfpz.buttons.del') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="(dialogType === 'add' ? $t('dsdfpz.diglogs.add') : $t('dsdfpz.diglogs.edt')) + ' ' + $t('routes.systemSettings.channel.titledf')" :close-on-click-modal="false">
      <el-form :model="settings" label-width="120px" label-position="left">
        <el-form-item :label="$t('dsdfpz.columns.id')" style="display: none"><el-input v-model="settings.merchant_id" /></el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.mer_id')">
          <el-input v-model="settings.mer_id" :placeholder="$t('dsdfpz.tips.mer_id')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.mer_key')">
          <el-input v-model="settings.mer_key" :placeholder="$t('dsdfpz.tips.mer_key')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.mer_key2')">
          <el-input v-model="settings.mer_key2" :placeholder="$t('dsdfpz.tips.mer_key2')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.mer_key3')">
          <el-input v-model="settings.mer_key3" :placeholder="$t('dsdfpz.tips.mer_key3')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.mer_key4')">
          <el-input v-model="settings.mer_key4" :placeholder="$t('dsdfpz.tips.mer_key4')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.pay_name_zh')">
          <el-input v-model="settings.pay_name_zh" :placeholder="$t('dsdfpz.tips.pay_name_zh')" />
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.pay_name')">
          <el-input v-model="settings.pay_name" :placeholder="$t('dsdfpz.tips.pay_name')" />
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
        <el-form-item :label="$t('dsdfpz.columns.is_self')">
          <el-select v-model="settings.is_self" :placeholder="$t('dsdfpz.tips.is_self')">
            <el-option :value="1" :label="$t('dsdfpz.options.yes')"></el-option>
            <el-option :value="0" :label="$t('dsdfpz.options.no')"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('dsdfpz.columns.is_xiaoshu')">
          <el-select v-model="settings.is_xiaoshu" :placeholder="$t('dsdfpz.tips.is_xiaoshu')">
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
import { addDFSettings, delDFSettings, edtDFSettings, getDFSettings } from '@/api/setting'

const defaultSettings = {
    id: '',
    mer_id: '',
    mer_key: '',
    mer_key2: '',
    mer_key3: '',
    mer_key4: '',
    pay_name_zh: '',
    pay_name: '',
    pay_url: '',
    channel_code: null,
    notify_ip: '',
    query_url: '',
    is_self: 0,
    is_xiaoshu: 0,
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
            var res = await getDFSettings(data);
            this.channelList = res.data;
            this.paginationData.total = res.total;
        },

        handleDel({ $index, row }) {
            this.$confirm(this.$t('dsdfpz.diglogs.confirmdel'), this.$t('routes.systemSettings.channel.titledf'), {
                type: 'warning',
                confirmButtonText: this.$t('dsdfpz.buttons.confirm'),
                cancelButtonText: this.$t('dsdfpz.buttons.cancel')
            }).then(async () => {
                try { await delDFSettings({ 'id': row.id }) } catch (err) { return }
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
                    res = await addDFSettings(this.settings);
                else
                    res = await edtDFSettings(this.settings);

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
