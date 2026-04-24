<template>
    <div class="app-container">
        <baseSearch ref="search" show-refresh :form-item-list="formItemList" :export-data="exportData"
            :export-bank-data="exportBankData" @search="getData" @export="getData" />
        <el-form>
            <el-button type="success" plain @click="handleCopy(count.successOrder)">{{ $t('method.df.buttons.success') }}: {{ count.successOrder }}</el-button>
            <el-button type="danger" plain @click="handleCopy(count.failOrder)">{{ $t('method.df.buttons.fail') }}: {{ count.failOrder }}</el-button>
            <el-button type="primary" plain @click="handleCopy(getRate())">{{ $t('method.df.buttons.rate') }}: {{ getRate() }}</el-button>
<!--            <el-button type="primary" plain @click="dialogVisible1=true">{{ $t('method.df.buttons.amount') }}: {{ count.amount }}</el-button>-->
            <el-button type="primary" plain @click="getMerchantFinish()">{{ $t('method.df.buttons.amount') }}: {{ count.amount }}</el-button>
<!--            <el-button type="warning" plain @click="dialogVisible0=true">{{ $t('method.df.buttons.processing') }}: {{ count.processing }}</el-button>-->
            <el-button type="warning" plain @click="getProcessing()">{{ $t('method.df.buttons.processing') }}: {{ count.processing }}</el-button>
            <el-button type="warning" plain @click="handleCopy(count.processing_amount)">{{ $t('method.df.buttons.processingAmount') }}: {{ count.processing_amount }}</el-button>
            <el-button type="primary" plain @click="handleCopy(count.realpay)">{{ $t('method.df.buttons.settle') }}: {{ count.realpay }}</el-button>
            <el-button type="primary" plain @click="handleCopy(count.earn_merchant)">{{ $t('method.df.buttons.merchantCommission') }}: {{ count.earn_merchant }}</el-button>
            <el-button type="primary" plain @click="handleCopy(count.earn_partner)">{{ $t('method.df.buttons.partnerCommission') }}: {{ count.earn_partner }}</el-button>
            <el-button type="primary" plain @click="handleCopy(count.earn_system)">{{ $t('method.df.buttons.platformProfit') }}: {{ count.earn_system }}</el-button>
            <el-button type="primary" @click="handleThirdPay()">{{ $t('method.df.buttons.thirdPay') }}</el-button>
            <el-button type="primary" @click="handleGetBatch()">{{ $t('method.df.buttons.batch_pd') }}</el-button>
            <el-button type="primary" @click="handleOrderPassBatch()">{{ $t('method.df.buttons.batch_confirm') }}</el-button>
            <el-button type="primary" @click="handleUploadReceiptBatch()">{{ $t('method.df.buttons.batch_upload_receipt') }}</el-button>
            <el-button type="primary" @click="handleExportUnpaidRecord()">{{ $t('method.df.buttons.export_unpaid_record') }}</el-button>
            <el-button type="success" plain>{{ $t('method.df.form.split_amount') }}: {{ count.split_amount }}</el-button>
        </el-form>
        <el-table :data="orderList" style="margin-top:6px;" stripe border
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}" @sort-change="sort_change" @selection-change="selectionChangeHandlerOrder">
            <el-table-column fixed="left" align="center" type="selection" width="50" :selectable="isRowSelectable" />
            <el-table-column fixed="left" align="center" :label="$t('method.df.columns.orderId')" width="200">
                <template slot-scope="scope">
                    {{ scope.row.code }}
                </template>
            </el-table-column>
            <!--
            <el-table-column fixed="left" align="left" :label="$t('method.df.form.split_remains')" width="200" show-overflow-tooltip>
                <template slot-scope="scope">
                    {{ scope.row.amount_remains }}
                </template>
            </el-table-column>
            -->
            <el-table-column fixed="left" align="left" :label="$t('method.df.columns.merchantId')" width="200" show-overflow-tooltip>
                <template slot-scope="scope">
                    {{ scope.row.merchant_code }}
                </template>
            </el-table-column>
            <el-table-column fixed="left" align="center" :label="$t('method.df.columns.amount')" width="100" sortable>
                <template slot-scope="scope">
                    {{ scope.row.amount }}
                </template>
            </el-table-column>
            <el-table-column fixed="left" align="center" :label="$t('method.df.columns.status')">
                <template slot-scope="scope">
                    <el-tag :type="getStatus(scope.row).type">
                        {{ getStatus(scope.row).name }}
                    </el-tag>
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.merchantId')">
                <template slot-scope="scope">
                    {{ scope.row.merchant_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.partnerId')">
                <template slot-scope="scope">
                    {{ scope.row.partner_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.bankId')">
                <template slot-scope="scope">
                    {{ scope.row.payment_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.ifsc')" width="120">
                <template slot-scope="scope">
                    {{ scope.row.ifsc }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.createTime')" width="160" sortable>
                <template slot-scope="scope">
                    {{ scope.row.time_create }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.acceptTime')" width="160" sortable>
                <template slot-scope="scope">
                    {{ scope.row.time_accept }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.payTime')" width="160">
                <template slot-scope="scope">
                    {{ scope.row.time_payed }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.successTime')" width="160" sortable>
                <template slot-scope="scope">
                    {{ scope.row.time_success }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.updateTime')" width="160" sortable>
                <template slot-scope="scope">
                    {{ scope.row.time_updated }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.thirdPartyId')">
                <template slot-scope="scope">
                    {{ scope.row.otherpay_id }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.thirdPartyName')">
                <template slot-scope="scope">
                    {{ scope.row.otherpay }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.bankName')">
                <template slot-scope="scope">
                    {{ scope.row.payment_bank }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.account')">
                <template slot-scope="scope">
                    {{ scope.row.payment_account }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.payeeName')">
                <template slot-scope="scope">
                    {{ scope.row.payment_name }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.settleAmount')">
                <template slot-scope="scope">
                    {{ scope.row.realpay }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.merchantRate')">
                <template slot-scope="scope">
                    {{ scope.row.merchant_rate }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.fee')">
                <template slot-scope="scope">
                    {{ scope.row.poundage }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.merchantProfit')">
                <template slot-scope="scope">
                    {{ scope.row.earn_merchant }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.partnerProfit')">
                <template slot-scope="scope">
                    {{ scope.row.earn_partner_self }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.platformProfit')">
                <template slot-scope="scope">
                    {{ scope.row.earn_system }}
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.columns.remarks')">
                <template slot-scope="scope">
                    {{ scope.row.sys_remark }}
                </template>
            </el-table-column>
            <!--
            <el-table-column align="center" :label="$t('method.df.form.split_flag')" width="120">
                <template slot-scope="scope">
                    <el-tag :type="scope.row.is_split === 1 ? 'success' : 'info'">
                        {{ scope.row.is_split === 1 ? $t('method.df.form.split_y') : $t('method.df.form.split_n') }}
                    </el-tag>
                </template>
            </el-table-column>
            <el-table-column align="center" :label="$t('method.df.form.is_del')" width="120">
                <template slot-scope="scope">
                    <el-tag :type="scope.row.is_del === 1 ? 'info' : 'success'">
                        {{ scope.row.is_del === 1 ? $t('method.df.form.del') : $t('method.df.form.no_del') }}
                    </el-tag>
                </template>
            </el-table-column>
            -->
            <el-table-column fixed="right" align="center" :label="$t('method.df.columns.operations')"  width="300">
                <template slot-scope="scope">
                    <!-- <el-button type="text" size="small">{{ $t('method.df.buttons.view') }}</el-button>
                    <el-button type="text" size="small">{{ $t('method.df.buttons.upload') }}</el-button>
                    <el-button type="text" size="small">{{ $t('method.df.buttons.callback') }}</el-button> -->

                    <el-button v-if="scope.row.is_split === 1" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleRevert(scope.row)">{{ $t('method.df.form.revert') }}</el-button>
                    <el-button v-if="scope.row.parent_id === '' && Number(scope.row.amount_remains) > 0 && [0, 1, 2].includes(scope.row.status) && scope.row.payment_id == null" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleSplit(scope.row.code, scope.row.amount_remains)">{{ $t('method.df.form.split') }}</el-button>
                    <el-button v-if="scope.row.is_split === 1" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleSplitView(scope.row.code)">{{ $t('method.df.form.sub_view') }}</el-button>

                    <el-button v-if="scope.row.is_split === 0 && scope.row.status === 0" type="success" size="mini"
                        style="margin-bottom: 10px;" @click="handleGet(scope.row)">GET</el-button>
                    <el-button v-if="scope.row.is_split === 0 && scope.row.status > 0 && scope.row.status < 3" type="warning" size="mini"
                        style="margin-bottom: 10px;" @click="handlePush(scope.row)">改派</el-button>

                    <el-button v-if="scope.row.is_split === 0 && scope.row.payment_img === 0 && scope.row.status !== 0" type="warning" size="mini"
                        style="margin-bottom: 10px;" @click="code=scope.row.code">
                        <!-- :action="'/prod-api/files/upload?code='+scope.row.code" -->
                        <el-upload :action="baseUrl + '/files/upload?code='+scope.row.code" accept="image" name="image"
                            :limit="1" :show-file-list="false" :on-success="updateSuccess" :on-error="updateError">上传凭证
                        </el-upload>
                    </el-button>
                    <el-button v-if="scope.row.is_split === 0 && scope.row.payment_img != 0" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleEdit(scope.row.code)">查看凭证</el-button>

                    <el-button v-if="scope.row.status >= 0" type="danger" size="mini"
                        style="margin-bottom: 10px;" @click="handleOrder(scope.row.code, 0)">驳回</el-button>

                    <el-button v-if="[1, 2].includes(scope.row.status) && !(scope.row.is_split === 1 && Number(scope.row.amount_remains) > 0)" type="warning" size="mini"
                        style="margin-bottom: 10px;" @click="handleOrder(scope.row.code, 1)">确认</el-button>

                    <el-button v-if="canShowRelease(scope.row)" type="danger" size="mini"
                        style="margin-bottom: 10px;" @click="handleRelease(scope.row)">{{ $t('method.df.buttons.release') }}</el-button>

                    <el-button v-if="[-2, 3].includes(scope.row.status) && scope.row.parent_id === ''" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleNotify(scope.row.code)">手动回调</el-button>

                    <el-button v-if="[3, 4].includes(scope.row.status)" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleReturnReceipt(scope.row)">回执</el-button>

                    <!-- <el-button v-if="scope.row.status == -1" type="danger" size="mini" @click="handleOrder(scope.row.code, 1)">补单</el-button> -->
                </template>
            </el-table-column>
        </el-table>


        <el-dialog :visible.sync="dialogVisible" title="凭证" :close-on-click-modal="false">
            <div class="block">
                <el-image :src="'/upload/'+ code+'.jpg'" fit="contain" />
            </div>
        </el-dialog>

        <div class="block" style="margin-top: 20px;">
            <el-pagination background :current-page="paginationData.page" :page-sizes="[10, 20, 50, 100]"
                :page-size="paginationData.size" layout="total, sizes, prev, pager, next, jumper"
                :total="paginationData.total" @size-change="handleSizeChange" @current-change="handleCurrentChange" />
        </div>

        <el-dialog :visible.sync="dialogVisibleThird" title="选择三方代付" :close-on-click-modal="false">
            <el-form label-width="80px" label-position="left">
                <el-form-item label="三方代付">
                    <el-select v-model="ThirdPayID" v-el-select-loadmore="loadmore" filterable default-first-option placeholder="请选择三方代付">
                        <el-option v-for="ThirdPay in ThirdPays" :key="ThirdPay.id"
                            :label="ThirdPay.id + '|' + ThirdPay.pay_name + '|' + ThirdPay.pay_name_zh"
                            :value="ThirdPay.id" />
                    </el-select>
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="dialogVisibleThird=false">取消</el-button>
                <el-button type="danger" @click="confirmThirdPay">确认</el-button>
            </div>
        </el-dialog>

        <!--        上传回执文件-->
        <el-dialog :visible.sync="UploadReceiptBatch" :title="$t('method.df.buttons.batch_upload_receipt')" :close-on-click-modal="false">
            <el-form label-width="80px" label-position="left">
                <el-form-item label="回执类型">
                    <el-radio-group v-model="receiptType" @change="receiptTypeChange">
                        <el-radio label="1" >银行</el-radio>
                        <el-radio label="2">三方代付</el-radio>
                    </el-radio-group>
                </el-form-item>
                <el-form-item :label="$t('method.df.receipt.selectBank')" v-show="showReceiptBanks">
                    <el-select v-model="BankName" @focus="loadbank" default-first-option :placeholder="$t('method.df.receipt.selectBank')" filterable>
                        <el-option v-for="bankInfo in Banks" :key="bankInfo.id"
                            :label="bankInfo.id + '|' + bankInfo.name "
                            :value="bankInfo.name" />
                    </el-select>
                </el-form-item>
                <el-form-item label="三方代付" v-show="showThirdPays">
                    <el-select v-model="thirdPayName" v-el-select-loadmore="loadmore" default-first-option placeholder="请选择三方代付">
                        <el-option v-for="thirdPay in ThirdPays" :key="thirdPay.id"
                            :label="thirdPay.id + '|' + thirdPay.pay_name + '|' + thirdPay.pay_name_zh"
                            :value="thirdPay.pay_name" />
                    </el-select>
                </el-form-item>
                <el-form-item :label="$t('method.df.receipt.uploadFile')">
                    <el-upload
                        class="upload-file"
                        drag
                        :action="baseUrl + '/files/upload?code=' + randomUploadCode"
                        :on-success="handleUploadSuccess"
                        :on-error="handleUploadError"
                        :file-list="fileList">
                        <i class="el-icon-upload"></i>
                        <div class="el-upload__text">{{ $t('method.df.receipt.DragTheFileHere') }} / <em>{{ $t('method.df.receipt.ClickToUpload') }}</em></div>
                        <div class="el-upload__tip" slot="tip">{{ $t('method.df.receipt.justOneFile') }}</div>
                    </el-upload>
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="UploadReceiptBatch=false">{{ $t('member.form.cancel') }}</el-button>
                <el-button type="danger" @click="confirmUpload">{{ $t('member.form.confirm') }}</el-button>
            </div>
        </el-dialog>

        <!--       导出代付记录-->
        <el-dialog :visible.sync="ExportUnpaidRecord" :title="$t('method.df.buttons.export_unpaid_record')" :close-on-click-modal="false">
            <el-form label-width="80px" label-position="left">
                <el-form-item :label="$t('method.df.form.bank_id')">
                    <el-input v-model="ExportBnakId" :placeholder="$t('method.df.form.bank_id')"></el-input>
                </el-form-item>
            </el-form>
            <div style="text-align:right;">
                <el-button type="primary" @click="ExportUnpaidRecord=false">{{ $t('member.form.cancel') }}</el-button>
                <el-button type="danger" @click="confirmExport">{{ $t('member.form.confirm') }}</el-button>
            </div>
        </el-dialog>

    <el-dialog :visible.sync="dialogVisible0" :title="$t('method.ds.orderManagement.dialog.processingOrders')">
        <el-table
            :data="merchant_processings"
            stripe
            style="width: 100%; margin-top: 30px;"
            border
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
        >
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.merchantId')" width="240" prop="merchant_id" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.processingOrders')" sortable prop="cnt" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.quantityDistributed')" sortable prop="status_0_count" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.amountDistributed')" sortable prop="status_0_total" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.paymentInProgress')" sortable prop="status_1_count" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.paymentInProgressAmount')" sortable prop="status_1_total" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.total')" sortable prop="total" />
        </el-table>
        <div style="text-align:right;">
            <el-button type="primary" @click="dialogVisible0=false">{{ $t('method.ds.orderManagement.dialog.back') }}</el-button>
            </div>
        </el-dialog>


        <!--       拆单-->
      <el-dialog
        :title="$t('method.df.form.order_split')"
        :visible.sync="dialogSplitVisible"
        width="30%"
        center
    >
        <el-form label-width="120px">
        <el-form-item :label="$t('method.df.form.order_number')">
            <el-input v-model="code" :placeholder="$t('method.df.form.enter_order_number')" readonly></el-input>
        </el-form-item>
        <el-form-item :label="$t('method.df.form.split_remains')">
            <el-input-number v-model="splitAmountRemains" :min="0" controls-position="right" disabled></el-input-number>
        </el-form-item>
        <el-form-item :label="$t('method.df.form.split_amount')">
            <el-input-number v-model="splitAmount" :min="0" controls-position="right"></el-input-number>
        </el-form-item>
        </el-form>
        <span slot="footer" class="dialog-footer">
        <el-button @click="dialogSplitVisible = false">{{ $t('method.df.form.cancel') }}</el-button>
        <el-button type="primary" @click="confirmSplitOrder">{{ $t('method.df.form.confirm_split') }}</el-button>
        </span>
    </el-dialog>

    <!--       子单查看-->
    <el-dialog
        :title="$t('method.df.form.split_details_title')"
        :visible.sync="dialogSplitDetailVisible"
        width="80%"
        center
    >
        <el-table
            :data="orderSplitList"
            stripe
            style="width: 100%"
            border
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
        >
            <el-table-column prop="code" :label="$t('method.df.columns.orderId')" align="center" fixed="left" width="200" />
            <el-table-column prop="merchant_code" :label="$t('method.df.columns.merchantId')" align="center" fixed="left" width="200" />
            <el-table-column prop="amount" :label="$t('method.df.columns.amount')" align="center" fixed="left" width="100" />
            <el-table-column prop="status" :label="$t('method.df.columns.status')" align="center" fixed="left" width="100" >
                <template slot-scope="scope">
                    <el-tag :type="getStatus(scope.row).type">
                        {{ getStatus(scope.row).name }}
                    </el-tag>
                </template>
            </el-table-column>
            <el-table-column prop="merchant_id" :label="$t('method.df.columns.merchantId')" align="center" />
            <el-table-column prop="partner_id" :label="$t('method.df.columns.partnerId')" align="center" />
            <el-table-column prop="payment_id" :label="$t('method.df.columns.bankId')" align="center" />
            <el-table-column prop="ifsc" :label="$t('method.df.columns.ifsc')" align="center" width="120" />
            <el-table-column prop="time_create" :label="$t('method.df.columns.createTime')" align="center" width="160" />
            <el-table-column prop="time_accept" :label="$t('method.df.columns.acceptTime')" align="center" width="160" />
            <el-table-column prop="time_payed" :label="$t('method.df.columns.payTime')" align="center" width="160" />
            <el-table-column prop="time_success" :label="$t('method.df.columns.successTime')" align="center" width="160" />
            <el-table-column prop="time_updated" :label="$t('method.df.columns.updateTime')" align="center" width="160" />
            <el-table-column prop="otherpay_id" :label="$t('method.df.columns.thirdPartyId')" align="center" />
            <el-table-column prop="otherpay" :label="$t('method.df.columns.thirdPartyName')" align="center" />
            <el-table-column prop="payment_bank" :label="$t('method.df.columns.bankName')" align="center" />
            <el-table-column prop="payment_account" :label="$t('method.df.columns.account')" align="center" />
            <el-table-column prop="payment_name" :label="$t('method.df.columns.payeeName')" align="center" />
            <el-table-column prop="realpay" :label="$t('method.df.columns.settleAmount')" align="center" />
            <el-table-column prop="merchant_rate" :label="$t('method.df.columns.merchantRate')" align="center" />
            <el-table-column prop="poundage" :label="$t('method.df.columns.fee')" align="center" />
            <el-table-column prop="sys_remark" :label="$t('method.df.columns.remarks')" align="center" />
            <el-table-column :label="$t('method.df.columns.operations')"  width="300" align="center"  fixed="right">
                <template slot-scope="scope">
                    <el-button v-if="scope.row.status === 0" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleThirdPay(scope.row.code)">{{ $t('method.df.buttons.thirdPay') }}</el-button>

                    <el-button v-if="scope.row.status === 0" type="success" size="mini"
                        style="margin-bottom: 10px;" @click="handleGet(scope.row)">GET</el-button>
                    <el-button v-if="scope.row.status > 0 && scope.row.status < 3" type="warning" size="mini"
                        style="margin-bottom: 10px;" @click="handlePush(scope.row)">改派</el-button>

                    <el-button v-if="scope.row.payment_img === 0 && scope.row.status !== 0" type="warning" size="mini"
                        style="margin-bottom: 10px;" @click="code=scope.row.code">
                        <el-upload :action="baseUrl + '/files/upload?code='+scope.row.code" accept="image" name="image"
                            :limit="1" :show-file-list="false" :on-success="updateSuccess" :on-error="updateError">上传凭证
                        </el-upload>
                    </el-button>
                    <el-button v-if="scope.row.payment_img === 1" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleEdit(scope.row.code)">查看凭证</el-button>

                    <el-button v-if="scope.row.status >= 0" type="danger" size="mini"
                        style="margin-bottom: 10px;" @click="handleOrder(scope.row.code, 0)">驳回</el-button>

                    <el-button v-if="[1, 2].includes(scope.row.status)" type="warning" size="mini"
                        style="margin-bottom: 10px;" @click="handleOrder(scope.row.code, 1)">确认</el-button>

                    <el-button v-if="[3, 4].includes(scope.row.status)" type="primary" size="mini"
                        style="margin-bottom: 10px;" @click="handleReturnReceipt(scope.row)">回执</el-button>
                </template>
            </el-table-column>
        </el-table>
        <span slot="footer" class="dialog-footer">
            <el-button type="primary" @click="subrefresh()">{{ $t('search.refresh') }}</el-button>
            <el-button @click="handleSplitClose()">{{ $t('method.df.form.close_button') }}</el-button>
        </span>
    </el-dialog>
    <el-dialog :visible.sync="dialogVisible1" :title="$t('method.ds.orderManagement.dialog.finishOrders')">
        <el-table
            :data="merchant_finish"
            stripe
            style="width: 100%; margin-top: 30px;"
            border
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
        >
        <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.table.merchantId')" width="240" prop="merchant_id" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.finishOrders')" sortable prop="cnt" />
            <el-table-column fixed="left" align="center" :label="$t('method.ds.orderManagement.dialog.total')" sortable prop="total" />
        </el-table>
        <div style="text-align:right;">
            <el-button type="primary" @click="dialogVisible1=false">{{ $t('method.ds.orderManagement.dialog.back') }}</el-button>
            </div>
        </el-dialog>
        <!-- 回执 -->
    <el-dialog title="回执" width="600px" :visible.sync="receiptInfo.show" :close-on-click-modal="false" @close="receiptInfo.reset()">
        <div class="receipt-info">
            <div class="receipt-info-amount">(PKR){{ receiptInfo.currentInfo ? receiptInfo.currentInfo.amount : '-' }}</div>
            <div class="receipt-info-content">
                <el-row type="flex" align="middle" class="receipt-info-row">
                    <el-col :span="12">Status</el-col>
                    <el-col :span="12">{{ getReceiptStatus(receiptInfo.currentInfo ? receiptInfo.currentInfo.status : null) }}</el-col>
                </el-row>

                <div class="receipt-info-line">{{ '*'.repeat(70) }}</div>
                <el-row type="flex" class="receipt-info-row">
                    <el-col :span="12">Beneficiary name</el-col>
                    <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.payment_name : '-' }}</el-col>
                </el-row>
                <el-row type="flex" align="middle" class="receipt-info-row">
                    <el-col :span="12">A/C No</el-col>
                    <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.payment_account : '-' }}</el-col>
                </el-row>
                <el-row type="flex" align="middle" class="receipt-info-row">
                    <el-col :span="12">Bank Name</el-col>
                    <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.ifsc : '-' }}</el-col>
                </el-row>
                <div class="receipt-info-line">{{ '*'.repeat(70) }}</div>
                <el-row type="flex" align="middle" class="receipt-info-row handwritten">
                    <el-col :span="12">Txid</el-col>
                    <el-col :span="12">
                        <span :class="{'empty': !receiptInfo.temporaryInformation.utr}">{{ receiptInfo.temporaryInformation.utr || 'Move mouse in to edit txid' }}</span>
                        <el-input size="small" v-model="receiptInfo.temporaryInformation.utr" placeholder="Please enter txid" />
                    </el-col>
                </el-row>
                <el-row type="flex" align="middle" class="receipt-info-row handwritten">
                    <el-col :span="12">Debit Account</el-col>
                    <el-col :span="12">
                        <span :class="{'empty': !receiptInfo.temporaryInformation.debitAccount}">{{ receiptInfo.temporaryInformation.debitAccount || 'Move mouse in to edit Debit Account' }}</span>
                        <el-input size="small" v-model="receiptInfo.temporaryInformation.debitAccount" placeholder="Please enter Debit Account" />
                    </el-col>
                </el-row>
                <el-row type="flex" align="middle" class="receipt-info-row">
                    <el-col :span="12">Sent Time</el-col>
                    <el-col :span="12">{{ receiptInfo.currentInfo ? receiptInfo.currentInfo.time_success : '-' }}</el-col>
                </el-row>
                <div style="text-align:right;">
                  <el-button type="primary" @click="receiptInfo.show = false">{{ $t('member.form.cancel') }}</el-button>
                  <el-button type="danger" @click="saveHuizhi">{{ $t('member.form.confirm') }}</el-button>
                </div>
            </div>
        </div>
    </el-dialog>

    </div>
</template>

<script>
import {
    getOrderdf,
    getOrderDfSplit,
    confirmSplitOrder,
    // handleOrderdf,
    handleOrderdfType1,
    handleOrderdfType2,
    handleOrderdfType3,
    handleOrderdfType4,
    handleOrderdfRevert,
    handleNotifydf,
    cancelOrderdf,
    getThirdPays,
    handleBatchThirdpay,
    handleBatchOrderdf,
    saveHuizhi, uploadReceiptBatch,
    getBankTypeByPaymentId,
    getDFMerchantFinishOrProcessing,
    releaseOrderdf
} from '@/api/order'
import {getBank_type} from "@/api/partner";
import { getDateTimePickerOptions } from '@/utils/pickerOptions';
    export default {
        name: 'Dfdd',
        directives: {
            /** 下拉框懒加载 */
            'el-select-loadmore': {
                bind(el, binding) {
                    const SELECTWRAP_DOM = el.querySelector('.el-select-dropdown .el-select-dropdown__wrap')
                    SELECTWRAP_DOM.addEventListener('scroll', function() {
                        const condition =
                            this.scrollHeight - this.scrollTop <= this.clientHeight
                        if (condition) {
                            binding.value()
                        }
                    })
                }
            }
        },
        data() {
            return {
                splitAmountRemains: 0,
                splitAmount: 0,
                merchant_processings: [],
                merchant_finish: [],
                ThirdPays: [], //三方代付列表
                Banks: [], //银行列表
                fileList: [],
                randomUploadCode: null,
                UploadReceiptBatch: false,
                ExportUnpaidRecord: false,
                receiptType: '1',
                showReceiptBanks: true,
                showThirdPays:false,
                thirdPayName: '',
                dialogVisibleThird: false,
                _ThirdPayData: null,
                ThirdPayPage: 1,
                ThirdPayPageSize: 10,
                orderCode: [], //订单code
                BankName: '',
                ExportBnakId: null,
                ThirdPayID: '',
                count: {
                    failOrder: 0,
                    successOrder: 0,
                    rate: 0,
                    processing: 0,
                    amount: 0,
                    realpay: 0,
                    earn_merchant: 0,
                    earn_partner: 0,
                    earn_system: 0
                },
                orderList: [],
                orderSplitList: [],
                order_field: 'id',
                sort: 'desc',
                code: '',
                dialogVisible: false,
                dialogSplitVisible: false,
                dialogSplitDetailVisible: false,
                dialogVisible0: false,
                dialogVisible1: false,
                merchant_finish_: false,
                processing_: false,
                params: {},
                currentId: 0,
                receiptInfo: {
                    show: false,
                    currentInfo: null,
                    reset() {
                        this.show = false
                        this.currentInfo = null
                        this.temporaryInformation = {
                            utr: '',
                            debitAccount: ''
                        }
                    },
                    temporaryInformation: {
                        utr: '',
                        debitAccount: ''
                    }
                },

                formItemList: [
    {
        label: this.$t('method.df.form.id'),
        type: 'input',
        param: 'code'
    },
    {
        label: this.$t('method.df.form.merchant_code'),
        type: 'input',
        param: 'merchant_code'
    },
    {
          label: this.$t('method.payment01.ds.form.bankName'),
          type: 'select',
          filterable: true,
          param: 'bank_type_id',
          selectOptions: [] // 这里的选项需要从其他地方加载
    },
    {
        label: this.$t('method.df.form.merchant_id'),
        type: 'input',
        param: 'merchant_id'
    },
    {
        label: this.$t('method.df.form.partner_id'),
        type: 'input',
        param: 'partner_id'
    },
    {
        label: this.$t('method.df.form.bank_id'),
        type: 'input',
        param: 'payment_id'
    },
    {
        label: this.$t('method.df.form.ifsc'),
        type: 'input',
        param: 'ifsc'
    },
    {
        label: this.$t('method.df.form.payment_name'),
        type: 'input',
        param: 'payment_name'
    },
    {
        label: this.$t('method.df.form.amount'),
        type: 'input',
        param: 'amount'
    },
    {
        label: this.$t('method.df.form.status'),
        type: 'select',
        selectOptions: [],
        param: 'status'
    },
    {
        label: this.$t('method.df.form.payment_img'),
        type: 'select',
        selectOptions: [
            { value: 0, label: this.$t('method.df.form.no_voucher') },
            { value: 1, label: this.$t('method.df.form.has_voucher') }
        ],
        param: 'payment_img'
    },
    {
        label: this.$t('method.df.form.amount_range'),
        type: 'input',
        param: 'amount_range_new'
    },
    // {
    //     label: this.$t('method.df.form.amount_range'),
    //     type: 'select',
    //     selectOptions: [
    //         { value: 1, label: this.$t('method.df.form.range_500') },
    //         { value: 2, label: this.$t('method.df.form.range_500_1000') },
    //         { value: 3, label: this.$t('method.df.form.range_1000_2000') },
    //         { value: 4, label: this.$t('method.df.form.range_2000_5000') },
    //         { value: 5, label: this.$t('method.df.form.range_5000_20000') },
    //         { value: 6, label: this.$t('method.df.form.range_20000_50000') },
    //         { value: 7, label: this.$t('method.df.form.range_above_50000') }
    //     ],
    //     param: 'amount_range'
    // },
    {
        label: this.$t('method.df.form.time_create'),
        type: 'dateTimePicker',
        pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
        param: 'time_create'
    },
    {
        label: this.$t('method.df.form.time_success'),
        type: 'dateTimePicker',
        pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
        param: 'time_success'
    },
    {
        label: this.$t('method.df.form.time_updated'),
        type: 'dateTimePicker',
        pickerOptions: getDateTimePickerOptions(this.$t.bind(this)),
        param: 'time_updated'
    },
    {
        label: this.$t('method.df.form.top_partner_id'),
        type: 'input',
        param: 'top_partner_id'
    },
    {
        label: '三方ID',
        type: 'input',
        param: 'otherpay_id'
    },
    // {
    //     label: this.$t('method.df.form.order_type'),
    //     type: 'select',
    //     selectOptions: [
    //         { value: 1, label: this.$t('method.df.form.main_order') },
    //         { value: 0, label: this.$t('method.df.form.sub_order') }
    //     ],
    //     param: 'is_split'
    // },
    {
        label: this.$t('method.df.form.order_type'),
        type: 'select',
        multiple: true,
        // defaultSelect: ['no', 'mo', 'so'],
        defaultSelect: [],
        selectOptions: [
            { value: 'no', label: this.$t('method.df.form.normal_order') },
            { value: 'mo', label: this.$t('method.df.form.main_order') },
            { value: 'so', label: this.$t('method.df.form.sub_order') },
        ],
        param: 'order_type'
    },
],
statusType: [
    {
        id: 0,
        name: this.$t('method.df.statusType.dispatching'),
        type: 'warning'
    },
    {
        id: 1,
        name: this.$t('method.df.statusType.pending_payment'),
        type: 'danger'
    },
    {
        id: 2,
        name: this.$t('method.df.statusType.pending_confirmation'),
        type: 'danger'
    },
    {
        id: 3,
        name: this.$t('method.df.statusType.callback'),
        type: 'primary'
    },
    {
        id: 4,
        name: this.$t('method.df.statusType.completed'),
        type: 'success'
    },
    {
        id: -1,
        name: this.$t('method.df.statusType.rejected'),
        type: 'info'
    },
    {
        id: -2,
        name: this.$t('method.df.statusType.callback_rejected'),
        type: 'info'
    },
    {
        id: 5,
        name: this.$t('method.df.statusType.processing'),
        type: 'danger'
    },
    {
        id: -999,
        name: this.$t('method.df.statusType.pending_payment'),
        type: 'danger',
        childset: [
            [ 0 ],
            [ 4 ],
            [ -2 ],
            [ 0, 4 ],
            [ -1, 4 ],
            [ -2, 4 ],
            [ 0, 1, 4 ],
        ]
    }
],
exportData: {
    tHeader: [
        this.$t('method.df.export.order_id'),
        this.$t('method.df.export.merchant_code'),
        this.$t('method.df.export.amount'),
        this.$t('method.df.export.status'),
        this.$t('method.df.export.merchant_id'),
        this.$t('method.df.export.partner_id'),
        this.$t('method.df.export.payment_id'),
        this.$t('method.df.export.otherpay_id'),
        this.$t('method.df.export.otherpay'),
        this.$t('method.df.export.ifsc'),
        this.$t('method.df.export.time_create'),
        this.$t('method.df.export.time_accept'),
        this.$t('method.df.export.time_payed'),
        this.$t('method.df.export.time_success'),
        this.$t('method.df.export.time_updated'),
        this.$t('method.df.export.payment_bank'),
        this.$t('method.df.export.payment_account'),
        this.$t('method.df.export.payment_name'),
        this.$t('method.df.export.realpay'),
        this.$t('method.df.export.merchant_rate'),
        this.$t('method.df.export.poundage'),
        this.$t('method.df.export.earn_merchant'),
        this.$t('method.df.export.earn_partner'),
        this.$t('method.df.export.earn_system'),
        this.$t('method.df.export.sys_remark')
    ],
    filterVal: [
        'code', 'merchant_code', 'amount', 'status', 'merchant_id', 'partner_id', 'payment_id', 'otherpay_id', 'otherpay',
        'ifsc', 'time_create', 'time_accept', 'time_payed', 'time_success', 'time_updated', 'payment_bank', 'payment_account',
        'payment_name', 'realpay', 'merchant_rate', 'poundage', 'earn_merchant', 'earn_partner_self', 'earn_system', 'sys_remark'
    ],
    list: [],
    filename: this.$t('method.df.export.filename')
},
exportBankData: {
    tHeader: [
        this.$t('method.df.export.order_id'),
        this.$t('method.df.export.amount'),
        this.$t('method.df.export.ifsc'),
        this.$t('method.df.export.account'),
        this.$t('method.df.export.name')
    ],
    filterVal: [
        'code', 'amount', 'ifsc', 'payment_account', 'payment_name'
    ],
    list: [],
    filename: this.$t('method.df.export.filename')
},

                paginationData: {
                    page: 1,
                    size: 10,
                    total: 0
                },
                baseUrl: process.env.VUE_APP_BASE_API,
                columnList: [
                { name: this.$t('method.ds.form.amount'), key: 'amount' },
                { name: this.$t('method.ds.form.time_create'), key: 'time_create' },
                { name: this.$t('method.df.columns.acceptTime'), key: 'time_accept' },
                { name: this.$t('method.df.columns.successTime'), key: 'time_success' },
                { name: this.$t('method.df.columns.updateTime'), key: 'time_updated' },

            ],
            }
        },
        created() {
            this.statusType.forEach(statusType => {
                if(statusType.id != -999) {
                    this.formItemList.find(item => item.param === 'status' && item.type === 'select').selectOptions.push({
                        value: statusType.id,
                        label: statusType.name
                    })
                }
            })
            this.randomUploadCode = Math.random().toString(36).substr(2, 9)
        },
        mounted() {
            this.$nextTick(() => {
                if (this.$refs.search?.searchData) {
                    this.$refs.search.searchData()
                }
            })
            this.getBankTypes()
        },
        methods: {
            /* 获取银行*/
            async getBankTypes() {
                const res = await getBank_type()
                const item = this.formItemList.find(item => item.param == 'bank_type_id')
                item.selectOptions.push(...res.data.map(b => ({ value: b.id, label: b.name })))
            },
            async confirmSplitOrder () {
                let data = {
                    code: this.code,
                    amount: this.splitAmount,
                };

                try { await confirmSplitOrder(data) } catch (err) { return }
                this.$notify({
                    title: this.$t('method.confirmRole.saveSuccess'),
                    dangerouslyUseHTMLString: true,
                    message: `
                        <div>code: ${this.code}</div>
                        <div>amount: ${this.splitAmount}</div>
                    `,
                    type: 'success'
                })
                this.dialogSplitVisible = false
                this.getData()
            },
            /* 确认新增或编辑*/
            async saveHuizhi() {
                this.receiptInfo.show = false
                let data = {
                    id: this.currentId,
                    huizhi_utr: this.receiptInfo.temporaryInformation.utr,
                    huizhi_debitAccount: this.receiptInfo.temporaryInformation.debitAccount
                };

                try { await saveHuizhi(data) } catch (err) { return }
                this.$notify({
                    title: this.$t('method.confirmRole.saveSuccess'),
                    dangerouslyUseHTMLString: true,
                    message: `
                        <div>utr: ${data.huizhi_utr}</div>
                        <div>debitAccount: ${data.huizhi_debitAccount}</div>
                    `,
                    type: 'success'
                })
                this.getData()
            },
            // 懒加载方法
            loadmore() {
                if (this._ThirdPayData.length == 0) return
                this.ThirdPayPage++
                this.getThirdPaysData()
            },
            async loadbank() {
                try {
                    const res = await getBank_type()
                    console.log(res)
                    this.Banks = res.data
                } catch (error) {
                    console.error('Error fetching banks:', error)
                }
        },
            /** 一次加载十条  获取三方代付数据*/
            async getThirdPaysData() {
                var data = {
                    'serchData': {
                        'status': 1
                    },
                    'size': 10,
                    'page': this.ThirdPayPage
                }
                try {
                    this._ThirdPayData = (await getThirdPays(data)).data
                    console.log(this._ThirdPayData)
                    if (this._ThirdPayData.length > 0) {
                        this.ThirdPays = this.ThirdPays.concat(this._ThirdPayData)
                    }
                } catch (e) {
                    return
                }
            },
            // 表格勾选
            async selectionChangeHandlerOrder(val) {
                var _this = this
                this.orderCode = []
                if (val.length !== 0) {
                    val.forEach(function(item) {
                        _this.orderCode.push(item.code)
                    });
                } else {
                    this.orderCode = []
                }

                // console.log(111, val, this.orderCode)
            },
            /* 处理三方代付 */
            async handleThirdPay(orderCodeOnRow) {
                if (orderCodeOnRow != null && orderCodeOnRow != "") {
                    this.orderCode.push(orderCodeOnRow);
                }

                if (this.orderCode.length == 0) {
                    this.$message({
                        type: 'error',
                        message: this.$t('method.no_order_selected')
                    })
                    return
                }
                this.dialogVisibleThird = true
                this.ThirdPayPage = 1
                this.ThirdPays = []
                this.getThirdPaysData()
            },
            /* 确认订单转为三方代付 */
            async confirmThirdPay() {
                var data = {
                    'id': this.ThirdPayID,
                    'codes': this.orderCode
                }
                var message = ''
                if (this.ThirdPayID === '') {
                    message = this.$t('method.choose_third_party_payment')
                }
                if (message) {
                    this.$message({
                        type: 'warning',
                        message: message
                    })
                } else {
                    var ThirdPay = this.ThirdPays.find(item => item.id == this.ThirdPayID)
                    try {
                        var lKey = this.orderCode.length > 1 ? "method.confirm_third_party_payment_batch" : "method.confirm_third_party_payment"
                        this.$confirm(this.$t(lKey, {
                            id: ThirdPay.id,
                            pay_name: ThirdPay.pay_name,
                            pay_name_zh: ThirdPay.pay_name_zh
                        }), this.$t('method.confirm'), {
                            type: 'warning',
                            confirmButtonText: this.$t('method.confirm'),
                            cancelButtonText: this.$t('method.cancel')
                        }).then(async () => {
                            try {
                                await handleBatchThirdpay(data)
                            } catch (err) {
                                this.$message({
                                    type: 'warning',
                                    message: this.$t('method.submit_failed_check_order')
                                })
                                return
                            }
                            this.$message({
                                type: 'success',
                                message: this.$t('method.submit_success')
                            })
                            this.getData()
                        }).catch(() => {})
                    } catch (e) {
                        return
                    }
                    this.dialogVisibleThird = false
                    this.ThirdPayID = ''
                }
            },
            /* 获取数据*/
            async getData(params, isExport = false) {
                if (params) {
                    this.params = params
                    this.paginationData.page = 1
                }
                var data = {
                    order_field: this.order_field,
                    sort: this.sort,
                    serchData: this.params
                }
                if (isExport) {
                    data.size = 0
                    data.page = 0
                } else {
                    data.size = this.paginationData.size
                    data.page = this.paginationData.page
                }
                // 去掉首尾空格
                // const input = this.params.amount_range_new.trim();
                const input = (this.params.amount_range_new || '').trim();
                // 空值逻辑
                if (input) {
                    // 检查格式是否符合 "数字-数字"
                    if (!/^\d+-\d+$/.test(input)) {
                    this.$message({
                        type: 'warning',
                        message: '输入格式不正确，请使用类似 11-22 的格式',
                    });
                    return;
                    }

                    // 分割成两个数字
                    const [min, max] = input.split('-').map(Number);

                    // 检查两个数字是否有效
                    if (min <= 0 || max <= 0) {
                    this.$message({
                        type: 'warning',
                        message: '金额必须大于 0',
                    });
                    return;
                    }

                    if (min >= max) {
                    this.$message({
                        type: 'warning',
                        message: '范围的后一个数字必须大于前一个数字',
                    });
                    return;
                    }
                }
                if(this.merchant_finish_ || this.processing_){
                    if(this.merchant_finish_){
                        data.merchant_finish = 1;
                    }else {
                        data.processing = 1;
                    }
                    this.merchant_finish_ = false;
                    this.processing_ = false;
                    const res = await getDFMerchantFinishOrProcessing(data)
                    if (isExport) {
                        this.exportData.list = res.data
                        this.$refs.search.exportExcel()
                    } else {
                        this.merchant_processings = res.merchant_processing?.map(item => ({
                                ...item,
                                status_0_count: +(item.status_0_count || 0),
                                status_0_total: +(item.status_0_total || 0),
                                status_1_count: +(item.status_1_count || 0),
                                status_1_total: +(item.status_1_total || 0),
                                total: +(item.total || 0)
                            })) || []
                        this.merchant_finish = res.merchant_finish?.map(item => ({
                                ...item,
                                total: +(item.total || 0)
                            })) || []
                    }
                }else {
                    const res = await getOrderdf(data)
                    if (isExport) {
                      this.exportData.list = res.data
                      this.exportBankData.list = res.data
                      this.$refs.search.exportExcel()
                    } else {
                      this.orderList = res.data
                      this.count = res.count
                      this.merchant_processings = res.merchant_processing?.map(item => ({
                        ...item,
                        status_0_count: +(item.status_0_count || 0),
                        status_0_total: +(item.status_0_total || 0),
                        status_1_count: +(item.status_1_count || 0),
                        status_1_total: +(item.status_1_total || 0),
                        total: +(item.total || 0),
                      })) || [];
                      this.merchant_finish = res.merchant_finish?.map(item => ({
                        ...item,
                        total: +(item.total || 0),
                      })) || [];
                      this.paginationData.total = res.total
                    }
                }
            },
           /* 获取数据*/
            async getMerchantFinish() {
                this.merchant_finish_ = true;
                this.getData()
                this.dialogVisible1 = true
            },

            async getProcessing() {
                this.processing_ = true;
                this.getData()
                this.dialogVisible0 = true
            },

            /* 排序*/
            async sort_change({ column }) {
                this.order_field = this.columnList.find(item => item.name === column.label).key
                if (column.order === 'ascending') {
                    this.sort = 'asc'
                } else if (column.order === 'descending') {
                    this.sort = 'desc'
                } else {
                    this.order_field = 'id'
                    this.sort = 'desc'
                }
                this.getData()
            },
            /* 计算成功率 */
            getRate() {
                var orders = this.count.failOrder + this.count.successOrder
                if (orders) {
                    return (this.count.successOrder / orders * 100).toFixed(4) + '%'
                }
                return '0%'
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
            /* 抢单*/
            async handleGetBatch() {
                if (this.orderCode.length === 0) {
                    this.$message({
                    type: 'error',
                    message: this.$t('method.select_error')
                    })
                    return
                }
                try {
                    // 提示用户输入一次
                    let { value } = await this.$prompt(this.$t('method.enter_qrid'), 'GET', {
                        type: 'warning',
                        confirmButtonText: this.$t('method.confirm'),
                        cancelButtonText: this.$t('method.cancel')
                    });

                    // 如果用户取消输入，则直接返回，不处理订单
                    if (!value) return;
                    try {
                        // 准备数据并处理订单
                        let data = {
                            codes: this.orderCode,
                            type: 4,
                            payment_id: value,
                        };
                        // 使用 await 处理订单
                        await handleBatchOrderdf(data);
                        // 统一显示处理结果
                        this.$message({
                            type: 'success',
                            message: `${this.$t('method.success')}`
                        });
                    } catch (err) {
                        console.error(err);
                    }
                    // 所有订单处理完成后获取数据
                    this.getData();
                } catch (err) {
                    // 如果提示框有错误或用户取消操作，捕获错误并退出
                    console.error(err);
                }
            },


            async handleUploadReceiptBatch() {
                this.UploadReceiptBatch = true

                this.ThirdPayPage = 1
                this.ThirdPays = []
                this.getThirdPaysData()
            },
            handleUploadSuccess(response, file) {
                // 处理上传成功的逻辑
                this.$message({
                    type: 'success',
                    message: this.$t('method.upload_success')
                })
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
                    'bank_name': this.BankName || this.thirdPayName,
                    'receipt_type': this.receiptType,
                    'third_pay_name': this.thirdPayName
                }
                const res = await uploadReceiptBatch(receipt_data);
                if ( res.code == 20000 ) {
                    this.$message({
                        type: 'success',
                        message: this.$t('method.submit_success')
                    })
                } else {
                    this.$message({
                        type: 'error',
                        message: res.message
                    })
                }

                // 关闭对话框
                this.UploadReceiptBatch = false;
                this.fileList = []
            },
            async handleExportUnpaidRecord() {
                this.ExportUnpaidRecord = true
            },

            async confirmExport(){
                var data = {
                    'payment_id': this.ExportBnakId
                }
                const res = await getBankTypeByPaymentId(data);

                var bank_name = res.data.name;
                if (bank_name !== 'YES BANK' && bank_name !== 'ICICI BANK' && bank_name !== 'IOB BANK') {
                    this.$message({
                        type: 'error',
                        message: this.$t('method.nonsupport_export_df_unpaid')
                    })
                    return;
                }
                // 关闭对话框
                this.ExportUnpaidRecord = false;
                // 替换成从服务器获取Excel文件URL的请求
                let url =  process.env.VUE_APP_BASE_API + '/order/exportOrderDfList?payment_id=' + this.ExportBnakId;
                // 使用浏览器下载功能开始下载Excel文件
                window.open(url);

            },

            receiptTypeChange(){
                console.log("receiptTypeChange e",this.receiptType)
                if(this.receiptType == 1){
                    this.showReceiptBanks = true;
                    this.showThirdPays = false;
                } else {
                    this.showReceiptBanks = false;
                    this.showThirdPays = true;
                }
            },

            /* 抢单*/
            handleGet(order) {
                this.$prompt(this.$t('method.enter_qrid'), 'GET', {
                    type: 'warning',
                    confirmButtonText: this.$t('method.confirm'),
                    cancelButtonText: this.$t('method.cancel')
                }).then(async ({ value }) => {
                    try {
                        var data = {
                            type: 4,
                            code: order.code,
                            payment_id: value,
                            parent_id: order.parent_id,
                        }
                        await handleOrderdfType4(data)
                    } catch (err) {
                        return
                    }
                    this.$message({
                        type: 'success',
                        message: this.$t('method.get_success')
                    })
                    this.getData()
                }).catch(() => {})
            },
             /* 指定派单 */
  handlePush(order) {
    this.$prompt(this.$t('method.enter_bankid'), this.$t('method.assign_order'), {
      type: 'warning',
      confirmButtonText: this.$t('method.confirm'),
      cancelButtonText: this.$t('method.cancel')
    }).then(async ({ value }) => {
      try {
        var data = {
          code: order.code,
          type: 3,
          status: order.status,
          payment_id: value,
          parent_id: order.parent_id
        }
        await handleOrderdfType3(data)
      } catch (err) {
        return
      }
      this.$message({
        type: 'success',
        message: this.$t('method.operation_successful')
      })
      this.getData()
    }).catch(() => {})
  },
  /* 上传成功 */
  async updateSuccess(response) {
    if (response.code == 20000) {
      try {
        await handleOrderdfType2({
          code: this.code,
          type: 2
        })
      } catch (err) {
        return
      }
      this.$message({
        type: 'success',
        message: this.$t('method.upload_success')
      })
      this.getData()
    } else {
      // 上传失败
      this.$message({
        type: 'error',
        message: this.$t('method.upload_failed')
      })
      return
    }
  },
  async updateError(response) {
    this.$message({
      type: 'error',
      message: response.toString().split('<title>')[1].split('</title>')[0]
    })
  },
  /* 查看凭证 */
  handleEdit(code) {
    this.dialogVisible = true
    this.checkStrictly = true
    this.code = code
  },
  /* 拆单 */
  handleSplit(code, amount_remains) {
    this.dialogSplitVisible = true
    this.code = code
    this.splitAmountRemains = amount_remains

  },
  /* 拆单明细 */
  async handleSplitView(code) {
    this.code = code
    await this.subrefresh();
    this.dialogSplitDetailVisible = true
  },
  /* 拆单明细 */
  handleSplitClose() {
    this.code = ''
    this.dialogSplitDetailVisible = false
    if(this.orderSplitList.length === 1)
        this.orderSplitList = []
  },
  /* 通过或拒绝订单 */
  async handleOrderPassBatch() {
    if (this.orderCode.length === 0) {
        this.$message({
        type: 'error',
        message: this.$t('method.select_error')
        })
        return
    }
    try {
        try {
            // 准备数据并处理订单
            let data = {
                codes: this.orderCode,
                type: 1
            };
            // 使用 await 处理订单
            await handleBatchOrderdf(data);
            // 统一显示处理结果
            this.$message({
                type: 'success',
                message: `${this.$t('method.success')}`
            });
        } catch (err) {
            console.error(err);
        }
        // 所有订单处理完成后获取数据
        this.getData();
    } catch (err) {
        // 如果提示框有错误或用户取消操作，捕获错误并退出
        console.error(err);
    }
  },
  /* 通过或拒绝订单 */
  handleOrder(code, type) {
    if (type === 1) {
      this.$confirm(this.$t('method.order_completed'), this.$t('method.confirmation'), {
        type: 'warning',
        confirmButtonText: this.$t('method.confirm'),
        cancelButtonText: this.$t('method.cancel')
      }).then(async () => {
        try {
          await handleOrderdfType1({
            code: code,
            type: 1
          })
        } catch (err) {
          return
        }
        this.$message({
          type: 'success',
          message: this.$t('method.order_completed')
        })
        this.getData()
      }).catch(() => {})
    } else {
      this.$prompt(this.$t('method.enter_reason_df'), this.$t('method.reject'), {
        type: 'warning',
        confirmButtonText: this.$t('method.confirm'),
        cancelButtonText: this.$t('method.cancel')
      }).then(async ({ value }) => {
        try {
          await cancelOrderdf({
            code: code,
            sys_remark: value
          })
        } catch (err) {
          return
        }
        this.$message({
          type: 'success',
          message: this.$t('method.order_rejected')
        })
        this.getData()
      }).catch(() => {})
    }
    this.getData()
  },
  /* 手动回调 */
  async handleNotify(code) {
    try {
      await handleNotifydf({
        code: code
      })
    } catch (err) {
      return
    }
    this.$message({
      type: 'success',
      message: this.$t('method.operation_successful')
    })
    this.getData()
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

  /** 回执 */
  handleReturnReceipt(row) {
    console.log(row)
    this.currentId = row.id
    this.receiptInfo.show = true
    this.receiptInfo.currentInfo = row
    this.receiptInfo.temporaryInformation.utr = row.utr
    this.receiptInfo.temporaryInformation.debitAccount = row.debit_account
  },
  getReceiptStatus(status) {
    switch (status) {
      case 3:
        return 'Callback'
      case 4:
        return 'Succeed'
      default:
        return '-'
    }
  },


            isRowSelectable(row) {
                return row.is_split === 0;
            },

            getStatus(row) {
                if (row.is_split === 0)
                    return this.statusType.find(item => item.id === row.status)
                else {
                    if (!this.hasValidField(row, 'childset'))
                        return this.statusType.find(item => item.id === row.status)
                    else {
                        var result = this.statusType.find(item => item.id === -999 && this.isEqualSetSorted(item.childset, row.childset))
                        if (result == null)
                            return this.statusType.find(item => item.id === row.status)
                    }
                }
            },
            isEqualSetSorted(arr1, arr2) {
                // 去重 + 排序
                const a = [...new Set(arr1)].sort((x, y) => x - y);
                const b = [...new Set(arr2)].sort((x, y) => x - y);

                // 长度不一致直接返回 false
                if (a.length !== b.length) return false;

                // 每一项逐个对比
                return a.every((val, idx) => val === b[idx]);
            },
            getReceiptStatus(status) {
                switch (status) {
                    case 3:
                        return 'Callback'
                    case 4:
                        return 'Succeed'
                    default:
                    return '-'
                }
            },
            async subrefresh() {
                const data = { code: this.code };
                const res = await getOrderDfSplit(data);
                this.orderSplitList = res.data;
            },
			hasValidField(obj, field) {
                const val = obj[field];
                return (
                    val !== undefined &&
                    val !== null &&
                    val !== '' &&
                    !(typeof val === 'string' && val.trim().length === 0) &&
                    !(Array.isArray(val) && val.length === 0)
                );
            },
            canShowRelease(row) {
                if (!row || !row.can_release) {
                    return false
                }
                const isParentOrder = row.is_split === 1 && (!row.parent_id || row.parent_id === '')
                if (isParentOrder && row.has_child_amount_in_use) {
                    return false
                }
                return true
            },
            async handleRelease(row) {
                try {
                    await this.$confirm(this.$t('method.release_confirm'), this.$t('method.confirmation'), {
                        confirmButtonText: this.$t('method.confirm'),
                        cancelButtonText: this.$t('method.cancel'),
                        type: 'warning',
                        dangerouslyUseHTMLString: true
                    })
                } catch (err) {
                    return
                }
                try {
                    await releaseOrderdf({
                        code: row.code
                    })
                    this.$message({
                        type: 'success',
                        message: this.$t('method.release_success')
                    })
                    this.getData()
                } catch (err) {
                    // error handled by interceptor
                }
            },
            isRowSelectable(row) {
                return row.is_split === 0;
            },
            getStatus(row) {
                if (row.is_split === 0 || [4, -1, -2].includes(row.status) || !this.hasValidField(row, 'childset')) {
                    return this.statusType.find(item => item.id === row.status)
                }

                var result = this.statusType.find(item => item.id === -999 && this.findMatch(row.childset, item.childset))
                if (result == null)
                    result = this.statusType.find(item => item.id === row.status);
                return result
            },
            findMatch(targetArr, childset) {
                for (const subset of childset) {
                    if (this.isSameSet(subset, targetArr)) {
                        return true
                    }
                }
                return false
            },
            isSameSet(arr1, arr2) {
                const a = [...new Set(arr1)].sort((x, y) => x - y);
                const b = [...new Set(arr2)].sort((x, y) => x - y);

                if (a.length !== b.length) return false;

                return a.every((v, i) => v === b[i]);
            },
            hasValidField(obj, field) {
                const val = obj[field];
                return (
                    val !== undefined &&
                    val !== null &&
                    val !== '' &&
                    !(typeof val === 'string' && val.trim().length === 0) &&
                    !(Array.isArray(val) && val.length === 0)
                );
            },
            handleRevert(row) {
                this.$confirm(this.$t('method.order_revert'), this.$t('method.confirmation'), {
                    type: 'warning',
                    confirmButtonText: this.$t('method.confirm'),
                    cancelButtonText: this.$t('method.cancel')
                }).then(async () => {
                    try {
                        await handleOrderdfRevert({
                            code: row.code
                        })
                    } catch (err) {
                        return
                    }
                    this.$message({
                        type: 'success',
                        message: this.$t('method.order_revert')
                    })
                    this.getData()
                }).catch(() => {})
            },
}
    }
</script>

<style scoped lang="scss">
.receipt-info {
    color: #000;
    padding: 5px 30px;
    font-weight: 500;
    .receipt-info-amount {
        text-align: center;
        font-size: 24px;
        margin-bottom: 15px;
    }
    .receipt-info-line {
        font-size: 18px;
        margin-bottom: 10px;
        margin: 5px 0;
    }
    .receipt-info-row {
        margin-bottom: 12px;
        height: 25px;
        &.handwritten {
            cursor: pointer;

            .el-input {
                display: none;
            }

            span.empty {
                color: #bbb;
                font-size: 12px;
                font-weight: 400;
            }

            &:hover {
                .el-input {
                    display: inline-block;
                }
                span {
                    display: none;
                }
            }
        }
    }
}
</style>
