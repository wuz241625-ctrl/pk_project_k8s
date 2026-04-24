<template>
  <div class="app-container">
    <baseSearch ref="search" :form-item-list="formItemList" :export-data="exportData" @search="getData" @export="getData" />
    <el-button type="primary" @click="handleImportBankRecords">{{ $t('bankrecord.import_record') }}</el-button>
    <el-button type="primary" plain @click="handleCopy(accountSum)">{{ $t('bankwithdrawal.account_sum') }}: {{accountSum}}</el-button>
    <el-table :data="record_list" style="width: 100%;margin-top:30px;" border stripe
      :header-cell-style="{ background: '#DCDFE6', color: '#606266' }"  @selection-change="selectionChangeHandlerOrder">
      <el-table-column type="selection"  align="center"  width="50" />
      <el-table-column align="center" :label="$t('method.Mslb.table.id')">
        <template slot-scope="scope">
          {{ scope.row.id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.time')" width="160">
        <template slot-scope="scope">
          {{ scope.row.time_create }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.bank_id')">
        <template slot-scope="scope">
          {{ scope.row.payment_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.partner_id')">
        <template slot-scope="scope">
          {{ scope.row.partner_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.amount')">
        <template slot-scope="scope">
          {{ scope.row.amount }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.utr')">
        <template slot-scope="scope">
          {{ scope.row.utr }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.admin_id')">
        <template slot-scope="scope">
          {{ scope.row.admin_id }}
        </template>
      </el-table-column>
      <el-table-column align="center" :label="$t('bankwithdrawal.s_bank_id')">
        <template slot-scope="scope">
          {{ scope.row.s_payment_id }}
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :visible.sync="ImportBankRecords" :title="$t('bankwithdrawal.import_withdrawal')" :close-on-click-modal="false">
      <el-form label-width="80px" label-position="left">
        <el-form-item :label="$t('bankwithdrawal.bank_id')">
          <el-input v-model="import_payment_id" maxlength="6" :placeholder="$t('bankwithdrawal.input_placeholder')" />
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
    importBankWithdrawal,
    getBankWithdrawal
} from '@/api/order'
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
export default {
    name: 'Yhjl',
    data() {
        return {
            ids: [], //ids
            accountSum: 0,
            id: '',
            new_record: {},
            record_list: [],
            dialogVisible: false,
            bank_type: [],
            formItemList: [
              { label: this.$t('bankwithdrawal.partner_id'), type: 'input', param: 'partner_id' },
              { label: this.$t('bankwithdrawal.bank_id'), type: 'input', param: 'payment_id' },
              { label: this.$t('bankwithdrawal.amount'), type: 'input', param: 'amount' },
              { label: this.$t('bankwithdrawal.s_bank_id'), type: 'input', param: 's_payment_id' },
              { label: this.$t('bankwithdrawal.time'), type: 'dateTimePicker', pickerOptions: getDateTimePickerOptions(this.$t.bind(this)), param: 'time_create' }
            ],
            params: {},
            baseUrl: process.env.VUE_APP_BASE_API,
            ImportBankRecords: false,
            fileList: [],
            import_payment_id: null,
            randomUploadCode: null,
            exportData: {
              tHeader: [
                this.$t('bankwithdrawal.bank_id'),
                this.$t('bankwithdrawal.partner_id'),
                this.$t('bankwithdrawal.amount'),
                this.$t('bankwithdrawal.utr'),
                this.$t('bankwithdrawal.admin_id'),
                this.$t('bankwithdrawal.time'),
                this.$t('bankwithdrawal.s_bank_id')
              ],
              filterVal: [
                'payment_id', 'partner_id', 'amount', 'utr', 'admin_id', 'time_create','s_payment_id'
              ],
              list: [],
              filename: this.$t('method.ds.export.bank_withdrawal_filename')
            },
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 200
            }
        }
    },
    created() {
        this.randomUploadCode = Math.random().toString(36).substr(2, 9)
        this.getData()
    },
    methods: {
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
        },

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
            const res = await getBankWithdrawal(data)

            if (isExport) {
                // 处理导出数据
                this.exportData.list = res.data
                this.$refs.search.exportExcel();
                return;
            }
            // 处理主数据
            this.record_list = res.data;
            this.paginationData.total = res.total;
            this.accountSum = res.accountSum;
        },
        /* 点击复制 */
        handleCopy(amount) {
            const oInput = document.createElement('input')
            oInput.value = amount
            document.body.appendChild(oInput)
            oInput.select() // 选择对象;
            document.execCommand('Copy') // 执行浏览器复制命令
            this.$message({
                type: 'success',
                message: this.$t('method.copy_success')
            })
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
          const res = await importBankWithdrawal(receipt_data);
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
