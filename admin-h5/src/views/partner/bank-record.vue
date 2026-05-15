<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" :export-data="exportData" @search="getData" @export="getData" />
    <el-button type="primary" @click="handleAdd">{{ $t('bankrecord.add') }}</el-button>
    <el-button type="primary" @click="handleImportBankRecords">{{ $t('bankrecord.import_record') }}</el-button>
    <el-button type="primary" @click="deleteUtrMemoBatchView()">{{ $t('method.Mslb.buttons.clear_utr') }}</el-button>
    <el-table :data="record_list" style="width: 100%;margin-top:30px;" border stripe
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"  @selection-change="selectionChangeHandlerOrder">
      <el-table-column type="selection"  align="center"  width="50" />
      <el-table-column align="center" :label="$t('method.Mslb.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.time')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.bankId')">
        <template slot-scope="scope">
          {{ scope.row.payment_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.partnerId')">
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.amount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.orderCode')" width="200px">
        <template slot-scope="scope">
          {{ scope.row.order_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.utr')">
        <template slot-scope="scope">
          {{ scope.row.utr }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.trans_id')" width="120">
        <template slot-scope="scope">
          {{ scope.row.trans_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.tradeType')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.trade_type == 0 ? 'info' : 'success'">
            {{ trade_type[scope.row.trade_type].name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.callback')">
        <template slot-scope="scope">
          <el-tag :type="scope.row.callback == 1 ? 'success' : 'danger'">
            {{ scope.row.callback == 1 ? $t('success') : $t('fail') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.code_bank')">
        <template slot-scope="scope">
          {{ scope.row.code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.ifsc')" width="120">
        <template slot-scope="scope">
          {{ scope.row.ifsc }}
        </template>
      </el-table-column>
      <el-table-column align="center" show-overflow-tooltip :label="$t('method.ds.form.formLabels.content')" width="300px">
        <template slot-scope="scope">
          {{ scope.row.content }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.adminId')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.ewCode')" width="200">
        <template slot-scope="scope">
          {{ scope.row.ew_code }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('method.ds.form.formLabels.memo')" width="200">
        <template slot-scope="scope">
          {{ scope.row.memo }}
        </template>
      </el-table-column>
      <el-table-column fixed="right" align="center" :label="$t('method.ds.form.formLabels.operation')" width="160">
        <template slot-scope="scope">
          <el-button v-if="scope.row.invalid != 1" type="danger" size="mini" @click="deleteUtrMemoView(scope.row.id)">{{ $t('method.ds.form.formLabels.delete') }}</el-button>
          <el-button v-if="scope.row.invalid == 1 && scope.row.callback != 1" type="warning" size="mini" @click="restoreUtrMemoView(scope.row.id)">↩️ {{ $t('method.restore_1') }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="dialogVisible" :title="$t('bankrecord.add_dialog_title')" :close-on-click-modal="false">
      <el-form :model="new_record" label-width="100px" label-position="left">
        <el-form-item :label="$t('bankrecord.payment_id')">
          <el-input v-model="new_record.payment_id" maxlength="6" :placeholder="$t('bankrecord.input_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('bankrecord.pay_phone')">
          <el-input v-model="new_record.utr" maxlength="12" :placeholder="$t('bankrecord.input_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('bankrecord.amount')">
          <el-input v-model="new_record.amount" :placeholder="$t('bankrecord.amount_placeholder')" />
          <!--span style="color: red;">{{ $t('bankrecord.warning_message') }}</span-->
        </el-form-item>
        <el-form-item :label="$t('bankrecord.trans_id')">
          <el-input v-model="new_record.trans_id" maxlength="12" :placeholder="$t('bankrecord.input_placeholder')" />
        </el-form-item>
        <!--el-form-item v-if="Number(new_record.amount) > 0" :label="$t('bankrecord.code')">
          <el-input v-model="new_record.code" maxlength="5" :placeholder="$t('bankrecord.auth_code_placeholder')" />
        </el-form-item>
        <el-form-item v-if="Number(new_record.amount) < 0" :label="$t('bankrecord.code_bank')">
          <el-input v-model="new_record.code" maxlength="4" :placeholder="$t('bankrecord.bank_last_4_digits_placeholder')" />
        </el-form-item>
        <el-form-item v-if="new_record.amount < 0" :label="$t('bankrecord.ifsc')">
          <el-input v-model="new_record.code" maxlength="5" :placeholder="$t('bankrecord.ifsc_placeholder')" />
        </el-form-item-->

      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{ $t('bankrecord.cancel') }}</el-button>
        <el-button type="danger" @click="confirmAdd">{{ $t('bankrecord.ok') }}</el-button>
      </div>
    </el-dialog>

    <el-dialog :visible.sync="ImportBankRecords" :title="$t('method.df.buttons.batch_upload_receipt')"
      :close-on-click-modal="false">
      <el-form label-width="80px" label-position="left">
        <el-form-item :label="$t('bankrecord.bank_id')">
          <el-input v-model="import_payment_id" maxlength="6" :placeholder="$t('bankrecord.input_placeholder')" />
        </el-form-item>
        <el-form-item :label="$t('method.df.receipt.uploadFile')">
          <el-upload class="upload-file" drag :action="baseUrl + '/partner/uploadBankStatement?code=' + randomUploadCode"
            :on-success="handleUploadSuccess" :on-error="handleUploadError" :file-list="fileList">
            <i class="el-icon-upload"></i>
            <div class="el-upload__text">{{ $t('method.df.receipt.DragTheFileHere') }} / <em>{{
              $t('method.df.receipt.ClickToUpload') }}</em></div>
            <div class="el-upload__tip" slot="tip">{{ $t('method.df.receipt.justOneFile') }}</div>
          </el-upload>
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="ImportBankRecords = false">{{ $t('member.form.cancel') }}</el-button>
        <el-button type="danger" @click="confirmUpload">{{ $t('member.form.confirm') }}</el-button>
      </div>
    </el-dialog>


    <el-dialog :visible.sync="deleteUtrMemo" :title="bankRecordAction === 'restore' ? $t('method.restore_1') : $t('method.ds.form.formLabels.delete')"
      :close-on-click-modal="false">
      <el-form label-width="80px" label-position="left">
        <el-form-item :label="$t('method.ds.form.formLabels.memo')">
          <el-input
            v-model="deleteMemo"
            type="textarea"
            :rows="3"
            maxlength="200"
            :placeholder="$t('bankrecord.input_placeholder')"
          />
        </el-form-item>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="deleteUtrMemo = false">{{ $t('member.form.cancel') }}</el-button>
        <el-button type="danger" @click="deleteUtrMemoSubmit">{{ $t('member.form.confirm') }}</el-button>
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
    getBank_type,
    getBank_recoed,
    addBank_recoed,
    delBank_recoed,
    restoreBank_recoed,
    import_bank_record,
    checkUtrPermission
} from '@/api/partner'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';

export default {
    name: 'Yhjl',
    data() {
        return {
            ids: [], //ids
            is_batch: false,
            deleteUtrMemo: false,
            bankRecordAction: 'void',
            deleteMemo: '',
            id: '',
            new_record: {},
            record_list: [],
            dialogVisible: false,
            bank_type: [],
            trade_type: [
              { id: 0, name: this.$t('method.ds.form.tradeType.fail') },
              { id: 1, name: this.$t('method.ds.form.tradeType.collect') },
              { id: 2, name: this.$t('method.ds.form.tradeType.pay') },
              { id: 3, name: this.$t('method.ds.form.tradeType.payReturn') },
              { id: 4, name: this.$t('method.ds.form.tradeType.payOther') }
            ],
            formItemList: [
              { label: this.$t('method.ds.form.formLabels.bankId'), type: 'input', param: 'payment_id' },
              { label: this.$t('method.ds.form.formLabels.partnerId'), type: 'input', param: 'partner_id' },
              { label: this.$t('method.ds.form.formLabels.amount'), type: 'input', param: 'amount' },
              { label: this.$t('method.ds.form.formLabels.utr'), type: 'input', param: 'utr' },
              { label: this.$t('method.ds.form.formLabels.trans_id'), type: 'input', param: 'trans_id' },
              { label: this.$t('method.ds.form.formLabels.code'), type: 'input', param: 'code' },
              { label: this.$t('method.ds.form.formLabels.orderCode'), type: 'input', param: 'order_code' },
              { label: this.$t('method.ds.form.formLabels.ewCode'), type: 'input', param: 'ew_code' },
              { label: this.$t('method.ds.form.formLabels.ifsc'), type: 'input', param: 'ifsc' },
              { label: this.$t('method.ds.form.formLabels.adminId'), type: 'input', param: 'admin_id' },
              { label: this.$t('method.ds.form.formLabels.tradeType'), type: 'select', selectOptions: [], param: 'trade_type' },
              {
                label: this.$t('method.ds.form.formLabels.callback'),
                type: 'select',
                selectOptions: [
                  { value: 0, label: this.$t('method.ds.form.callbackOptions.fail') },
                  { value: 1, label: this.$t('method.ds.form.callbackOptions.success') }
                ],
                param: 'callback'
              },
              { label: this.$t('method.ds.form.formLabels.time'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' }
            ],
            params: {},
            baseUrl: process.env.VUE_APP_BASE_API,
            ImportBankRecords: false,
            fileList: [],
            import_payment_id: null,
            randomUploadCode: null,
            exportData: {
              tHeader: [
                this.$t('method.ds.form.payment_id'),
                this.$t('method.ds.form.partner_id'),
                this.$t('method.ds.form.amount'),
                this.$t('method.ds.form.trade_type'),
                this.$t('method.ds.form.callback'),
                this.$t('method.ds.form.order_code'),
                this.$t('method.ds.form.utr'),
                this.$t('method.ds.form.code'),
                this.$t('method.ds.form.ifsc'),
                this.$t('method.ds.form.ew_code'),
                this.$t('method.ds.form.admin_id'),
                this.$t('method.ds.form.trans_id')
              ],
              filterVal: [
                'payment_id', 'partner_id', 'amount', 'trade_type', 'callback', 'order_code', 'utr', 'code', 'ifsc', 'ew_code', 'admin_id', 'trans_id'
              ],
              list: [],
              filename: this.$t('method.ds.export.bank_record')
            },
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            }
        }
    },
    created() {
      this.trade_type.forEach(statusType => {
            this.formItemList.find(item => item.label === this.$t('method.ds.form.formLabels.tradeType')).selectOptions
                .push({
                    value: statusType.id,
                    label: statusType.name
                })
        })
        this.randomUploadCode = Math.random().toString(36).substr(2, 9)
        this.getBank()

    },
    methods: {
        async deleteUtrMemoBatchView() {
          if (this.ids.length == 0) {
              this.$message({
                  type: 'error',
                  message: this.$t('method.no_data_selected')
              })
              return
          }
          this.id = this.ids
          this.bankRecordAction = 'void'
          this.deleteUtrMemo = true
          this.is_batch = true
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
        async deleteUtrMemoSubmit() {
          try {
                const request = this.bankRecordAction === 'restore' ? restoreBank_recoed : delBank_recoed
                await request({
                    'id': this.id,
                    'memo': this.deleteMemo
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.bankRecordAction === 'restore' ? this.$t('method.restore_success') : this.$t('method.delete_success')
            })
            this.deleteUtrMemo = false
            this.deleteMemo = ''
            this.getData()
        },
        async deleteUtrMemoView(id) {
          this.id = id
          this.bankRecordAction = 'void'
          this.deleteMemo = ''
          this.deleteUtrMemo = true
        },
        async restoreUtrMemoView(id) {
          this.id = id
          this.bankRecordAction = 'restore'
          this.deleteMemo = ''
          this.deleteUtrMemo = true
        },
        /* 获取银行*/
        async getBank(params) {
            const res = await getBank_type()
            this.bank_type = res.data
            this.getData()
        },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
                this.paginationData.page = 1
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
            const res = await getBank_recoed(data)
            if (isExport) {
                this.paginationData.total = res.total
                this.exportData.list = res.data
                this.$refs.search.exportExcel()
            } else {
                this.record_list = res.data
                this.paginationData.total = res.total
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
        /* 新增记录*/
        handleAdd() {
            this.dialogVisible = true
            this.new_record = {}
        },
        /* 确认编辑*/
    async confirmAdd() {
        try {
            await addBank_recoed(this.new_record)
        } catch (err) {
            return
        }
        const {
            payment_id,
            amount
        } = this.new_record
        this.dialogVisible = false
        this.$notify({
            title: this.$t('method.save_success'),
            dangerouslyUseHTMLString: true,
            message: `
        <div>ID: ${payment_id}</div>
        <div>${this.$t('method.name')}: ${amount}</div>
      `,
            type: 'success'
        })
        this.getData()
    },
    handleDelete({ $index, row }) {
        this.$confirm(this.$t('method.confirm_delete_record'), this.$t('method.delete_1'), {
            type: 'warning',
            confirmButtonText: this.$t('method.confirm'),
            cancelButtonText: this.$t('method.cancel')
        }).then(async () => {
            try {
                await delBank_recoed({
                    'id': row.id
                })
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.delete_success')
            })
            this.getData()
      }).catch(() => { })
    },
    async handleImportBankRecords() {
      this.ImportBankRecords = true

      this.randomUploadCode = Math.random().toString(36).substr(2, 9)
    },
    handleUploadSuccess(response, file) {
      // 处理上传成功的逻辑
      this.$message({
          type: 'success',
          message: this.$t('method.upload_success')
      })
      this.fileList = []
      this.fileList.push(file);
    },
    handleUploadError(err, file) {
      // 处理上传失败的逻辑
      this.$message({
          type: 'success',
          message: this.$t('method.upload_success')
      })
    },
    async confirmUpload() {
      if (this.fileList.length === 0) {
          this.$message.error('请先选择文件!');
          return;
      }

      var receipt_data = {
          'filename': this.fileList[0].name,
          'random_code': this.randomUploadCode,
          'payment_id': this.import_payment_id
      }
      const res = await import_bank_record(receipt_data);
      console.log("res...",res)
      if ( res.code == 20000 ) {
          this.$message({
              type: 'success',
              message: this.$t('method.submit_success')
          })
          this.getData()
      } else {
          this.$message({
              type: 'error',
              message: res.message
          })
      }

      // 关闭对话框
      this.ImportBankRecords = false;
      this.fileList = []
    },
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
