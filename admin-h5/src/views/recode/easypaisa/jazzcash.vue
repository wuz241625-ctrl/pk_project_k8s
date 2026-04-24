<template>
    <div class="app-container">
        <baseSearch
            ref="search"
            :form-item-list="formItemList"
            @search="getData"
        />
        <el-table
            :data="recordList"
            stripe
            style="width: 100%;margin-top:30px;"
            border
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
        >
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accno')">
                <template slot-scope="scope">
                    {{ scope.row.accno }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accountName')">
                <template slot-scope="scope">
                    {{ scope.row.accountName }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accountNameUr')">
                <template slot-scope="scope">
                    {{ scope.row.accountNameUr }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accountBalance')">
                <template slot-scope="scope">
                    {{ scope.row.accountBalance }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accountStatus')">
                <template slot-scope="scope">
                    {{ scope.row.accountStatus }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.IBAN')">
                <template slot-scope="scope">
                    {{ scope.row.IBAN }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accountLevel')">
                <template slot-scope="scope">
                    {{ scope.row.accountLevel }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.itemizedBill.table.accountLevel')">
                <template slot-scope="scope">
                    <el-button @click="clickDownload(scope.row)">下载明细账单</el-button>
                </template>
            </el-table-column>
        </el-table>
        <el-dialog
            :title="$t('method.itemizedBill.dialogForm.dialogTitle')"
            :visible.sync="downloadBool"
            top="200px"
            width="600px">
            <div>
                <el-form :model="downloadForm" ref="downloadFormRef" label-width="100px" class="demo-ruleForm">
                    <el-form-item :label="$t('method.itemizedBill.dialogForm.timeLabel')" prop="region" label-width="200">
                        <el-date-picker
                            v-model="downloadForm.time"
                            :picker-options="pickerOptionRang"
                            :default-time="['00:00:00', '23:59:59']"
                            value-format="yyyy-MM-dd HH:mm:ss"
                            type="datetimerange"
                            range-separator="至"
                            :start-placeholder="$t('method.itemizedBill.dialogForm.startTime')"
                            :end-placeholder="$t('method.itemizedBill.dialogForm.endTime')">
                        </el-date-picker>
                    </el-form-item>
                </el-form>
            </div>
            <span slot="footer" class="dialog-footer">
                <el-button @click="downloadBool = false">{{ $t('method.itemizedBill.dialogForm.cancel') }}</el-button>
                <el-button type="primary"  :loading="submitBtnLoading" @click="downloadDialogSubmit">{{ $t('method.itemizedBill.dialogForm.submit') }}</el-button>
              </span>
        </el-dialog>
    </div>
</template>

<script>
import {
    downloadBill, downloadBillJCB,
    getAccountList, getAccountListJCB
} from '@/api/record'


export default {
    name: 'Yels',
    data() {
        return {
            pickerOptionRang:{
                disabledDate:(time)=>{
                    return time.getTime() > Date.now();
                }
            },
            downloadForm:{},
            downloadBool:false,
            submitBtnLoading:false,
            recordList: [], // 数据表
            formItemList: [
                { label: 'method.itemizedBill.searchForm.phoneNumber', type: 'input', param: 'phone' },
            ],
            params: {},
        }
    },
    created() {
        // this.getData()
    },
    methods: {
        clickDownload(row){
            this.downloadBool = true
            row = {...row}
            row.phone = this.params.phone
            this.clickRow = row
        },
        async downloadDialogSubmit(){
            if (!this.downloadForm.time || this.downloadForm.time.length === 0) {
                this.$message.warning('please check' + this.$t('method.itemizedBill.dialogForm.startTime') + ' and ' + this.$t('method.itemizedBill.dialogForm.endTime'))
                return
            }
            this.submitBtnLoading = true
            let params = {
                phone:this.clickRow.phone,
                accno:this.clickRow.accno,
                fromDateTime:this.downloadForm.time[0],
                toDateTime:this.downloadForm.time[1]
            }
            const res = await downloadBillJCB(params)
            if (res.code == 20000){
                let raw = window.atob(res.data.fileData);
                let rawLength = raw.length;
                let uInt8Array = new Uint8Array(rawLength);
                for (let i = 0; i < rawLength; ++i) {
                    uInt8Array[i] = raw.charCodeAt(i);
                }
                let blob = new Blob([uInt8Array], { type: 'pdf' });
                //放在一个a标签里，通过点击下载
                let aLink = document.createElement("a");
                // let blob = this.base64ToBlob(content);
                let evt = document.createEvent("HTMLEvents");
                evt.initEvent("click", true, true);
                aLink.download =  this.clickRow.accno + res.data.fileName;
                aLink.href = URL.createObjectURL(blob);
                aLink.click()
                this.downloadBool = false
            }
            this.submitBtnLoading = false
        },
        /* 获取数据*/
        async getData(params, isExport = false) {
            if (params) {
                this.params = params
            }
            const res = await getAccountListJCB(this.params)
            if (res.code == 20000) {
                this.recordList = res.data
            }
        },
    }
}
</script>
