<template>
    <div class="app-container">

        <!-- 顶部标题和开关 -->
        <div class="header-section">
            <h2 class="page-title">自动代付监控面板 <span v-if="coolDownTimer.minutes" style="color: red;font-size: 14px">冷静期:{{ coolDownTimer.minutes * 60 + coolDownTimer.seconds * 1 + '秒' }}</span></h2>
            <div class="auto-switch">
                <div class="switch-box">
                    <span>自动代付开关&nbsp;&nbsp;</span>
                    <el-switch
                        v-model="autoPaymentEnabled"
                        @change="handleSwitchChange"
                        active-color="#13ce66"
                        inactive-color="#ff4949">
                    </el-switch>
                </div>
                <div class="cool-down-box"  @click="coolDownSetting">
                    <span>冷静期设置&nbsp;&nbsp;</span>
                    <i class="el-icon-s-tools"></i>
                </div>
                <div class="cool-down-box"  @click="orderCoolDownSetting">
                    <span>订单冷静期设置&nbsp;&nbsp;</span>
                    <i class="el-icon-s-tools"></i>
                </div>
            </div>
        </div>

        <!-- 统计卡片区域 -->
        <div class="stats-section">
            <el-row :gutter="20">
                <el-col :span="8">
                    <div class="stat-card">
                        <div class="stat-icon blue">
                            <i class="el-icon-wallet"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-title">今日代付</div>
                            <div class="stat-value">₨{{ formatNumber(stats.todayAmount) }}</div>
                            <div class="stat-trend positive">
                                <i class="el-icon-top"></i>
                                比昨日增长 {{ stats.todayGrowth }}%
                            </div>
                        </div>
                    </div>
                </el-col>
                <el-col :span="8">
                    <div class="stat-card">
                        <div class="stat-icon yellow">
                            <i class="el-icon-document"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-title">今日笔数</div>
                            <div class="stat-value">{{ formatNumber(stats.todayCount) }}</div>
                            <div class="stat-trend positive">
                                <i class="el-icon-top"></i>
                                比昨日增长 {{ stats.todayCountGrowth }}%
                            </div>
                        </div>
                    </div>
                </el-col>
                <el-col :span="8">
                    <div class="stat-card">
                        <div class="stat-icon gray">
                            <i class="el-icon-date"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-title">昨日代付</div>
                            <div class="stat-value">₨{{ formatNumber(stats.yesterdayAmount) }}</div>
                            <div class="stat-desc">笔数 {{ formatNumber(stats.yesterdayCount) }}</div>
                        </div>
                    </div>
                </el-col>
            </el-row>

            <el-row :gutter="20" style="margin-top: 20px;">
                <el-col :span="8">
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <i class="el-icon-money"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-title">总代付</div>
                            <div class="stat-value">₨{{ formatNumber(stats.totalAmount) }}</div>
                            <div class="stat-desc">今日增长 {{ formatNumber(stats.totalDailyIncrease) }}</div>
                        </div>
                    </div>
                </el-col>
                <el-col :span="8">
                    <div class="stat-card">
                        <div class="stat-icon purple">
                            <i class="el-icon-s-data"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-title">总笔数</div>
                            <div class="stat-value">{{ formatNumber(stats.totalCount) }}</div>
                            <div class="stat-desc">今日增长 {{ formatNumber(stats.totalCountIncrease) }}</div>
                        </div>
                    </div>
                </el-col>
                <el-col :span="8">
                    <div class="stat-card">
                        <div class="stat-icon green">
                            <i class="el-icon-success"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-title">成功率</div>
                            <div class="stat-value">{{ stats.successRate }}%</div>
                            <div class="stat-desc">今日增长 {{ formatNumber(stats.successRateIncrease) }}</div>
                        </div>
                    </div>
                </el-col>
            </el-row>
        </div>

        <!-- 搜索过滤区域 -->
        <div class="search-section">
            <el-row :gutter="20">
                <el-col :span="4">
                    <el-input v-model="searchParams.orderCode" placeholder="订单号" clearable>
                        <i slot="prefix" class="el-input__icon el-icon-search"></i>
                    </el-input>
                </el-col>
                <el-col :span="4">
                    <el-input v-model="searchParams.merchantId" placeholder="码商ID" clearable>
                        <i slot="prefix" class="el-input__icon el-icon-user"></i>
                    </el-input>
                </el-col>
                <el-col :span="4">
                    <el-select v-model="searchParams.status" placeholder="状态">
                        <el-option label="待处理" :value="0"/>
                        <el-option label="处理中" :value="1"/>
                        <el-option label="待确认" :value="2"/>
                        <el-option label="成功" :value="3"/>
                        <el-option label="通知商户已到账" :value="4"/>
                        <!--                        <el-option label="异常按成功处理" :value="5"/>-->
                        <el-option label="失败" :value="-1"/>
                    </el-select>
                </el-col>
                <el-col :span="4">
                    <el-date-picker
                        v-model="searchParams.startDate"
                        type="date"
                        placeholder="开始日期"
                        format="yyyy/MM/dd"
                        value-format="yyyy-MM-dd">
                    </el-date-picker>
                </el-col>
                <el-col :span="4">
                    <el-date-picker
                        v-model="searchParams.endDate"
                        type="date"
                        placeholder="结束日期"
                        format="yyyy/MM/dd"
                        value-format="yyyy-MM-dd">
                    </el-date-picker>
                </el-col>
                <el-col :span="2">
                    <el-button type="primary" icon="el-icon-search" @click="handleSearch">查询</el-button>
                </el-col>
                <el-col :span="2">
                    <el-button icon="el-icon-refresh" @click="handleReset">重置</el-button>
                </el-col>
            </el-row>
        </div>

        <!-- 数据表格 -->
        <div class="table-section">
            <el-table :data="monitorList" stripe border
                :header-cell-style="{ background:'#DCDFE6', color:'#606266' }">

                <el-table-column align="center" label="订单号" width="180">
                    <template slot-scope="scope">
                        {{ scope.row.orderCode }}
                    </template>
                </el-table-column>

                <el-table-column align="center" label="码商ID" width="120">
                    <template slot-scope="scope">
                        {{ scope.row.merchantId }}
                    </template>
                </el-table-column>

                <el-table-column align="center" label="金额" width="120">
                    <template slot-scope="scope">
                        ₨{{ formatNumber(scope.row.amount) }}
                    </template>
                </el-table-column>

                <el-table-column align="center" label="最近时间" width="160">
                    <template slot-scope="scope">
                        {{ scope.row.lastTime }}
                    </template>
                </el-table-column>

                <el-table-column align="center" label="状态" width="120">
                    <template slot-scope="scope">
                        <el-tag :type="getStatusType(scope.row.status)">
                            {{ getStatusText(scope.row.status) }}
                        </el-tag>
                    </template>
                </el-table-column>

                <el-table-column align="center" label="备注" show-overflow-tooltip>
                    <template slot-scope="scope">
                        {{ scope.row.remark }}
                    </template>
                </el-table-column>

                <el-table-column align="center" label="操作" width="100">
                    <template slot-scope="scope">
                                                <el-button
                            type="text"
                            @click="viewDetails(scope)"
                            :disabled="!scope.row.orderCode">
                            详情
                        </el-button>
                    </template>
                </el-table-column>
            </el-table>
        </div>

        <!-- 分页 -->
        <div class="pagination-section">
            <el-pagination
                background
                :current-page="paginationData.page"
                :page-sizes="[10, 20, 50, 100]"
                :page-size="paginationData.size"
                layout="total, sizes, prev, pager, next, jumper"
                :total="paginationData.total"
                @size-change="handleSizeChange"
                @current-change="handleCurrentChange" />
        </div>

        <!-- 紧急停止按钮 - 已隐藏 -->
        <div class="emergency-section" v-show="false">
            <el-button
                type="danger"
                size="large"
                icon="el-icon-warning-outline"
                @click="handleEmergencyStop"
                :loading="emergencyLoading">
                紧急停止
            </el-button>
        </div>

        <!-- 详情对话框 -->
        <el-dialog :visible.sync="dialogVisible" title="订单详情" width="90%">
            <el-tabs v-model="activeTab" type="border-card">
                <!-- 基本信息Tab -->
                <el-tab-pane label="订单信息" name="basic">
            <el-descriptions :column="2" border>
                <el-descriptions-item label="订单编号">{{ dialogData.orderCode }}</el-descriptions-item>
                <el-descriptions-item label="码商ID">{{ dialogData.merchantId }}</el-descriptions-item>
                <el-descriptions-item label="金额">₨{{ formatNumber(dialogData.amount) }}</el-descriptions-item>
                <el-descriptions-item label="状态">{{ getStatusText(dialogData.status) }}</el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ dialogData.createTime }}</el-descriptions-item>
                        <el-descriptions-item label="最近时间">{{ dialogData.lastTime || '-' }}</el-descriptions-item>
                        <el-descriptions-item label="备注" span="2">{{ dialogData.remark || '-' }}</el-descriptions-item>
            </el-descriptions>
                </el-tab-pane>

                <!-- 交易记录Tab -->
                <el-tab-pane name="logs">
                    <span slot="label">
                        <i class="el-icon-document"></i>
                        交易记录
                        <el-badge :value="operationLogs.length" :hidden="operationLogs.length === 0" class="item">
                        </el-badge>
                    </span>

                    <div v-if="operationLogs.length === 0" class="no-logs">
                        <el-empty description="暂无交易记录">
                            <el-button size="small" @click="refreshLogs" :loading="logsLoading">
                                <i class="el-icon-refresh"></i>
                                刷新记录
                            </el-button>
                        </el-empty>
                    </div>

                    <div v-else>
                        <div class="logs-header">
                            <div class="logs-summary">
                                <el-tag type="info" size="medium">
                                    <i class="el-icon-tickets"></i>
                                    共 {{ operationLogs.length }} 条交易记录
                                </el-tag>
                                <el-button
                                    size="mini"
                                    type="text"
                                    @click="refreshLogs"
                                    :loading="logsLoading"
                                    style="margin-left: 10px;">
                                    <i class="el-icon-refresh"></i>
                                    刷新
                                </el-button>
                            </div>
                        </div>

                        <el-table
                            :data="operationLogs"
                            stripe
                            size="mini"
                            max-height="450"
                            style="margin-top: 15px;">

                            <el-table-column prop="created_at" label="交易时间" width="160" fixed="left">
                                <template slot-scope="scope">
                                    <div class="time-cell">
                                        <i class="el-icon-time"></i>
                                        <span>{{ scope.row.created_at }}</span>
                                    </div>
                                </template>
                            </el-table-column>

                            <el-table-column prop="operation_type" label="交易类型" width="100">
                                <template slot-scope="scope">
                                    <el-tag :type="getOperationTypeTag(scope.row.operation_type)" size="mini">
                                        {{ getOperationTypeText(scope.row.operation_type) }}
                                    </el-tag>
                                </template>
                            </el-table-column>

                            <el-table-column prop="status" label="交易状态" width="100">
                                <template slot-scope="scope">
                                    <el-tag :type="getLogStatusTag(scope.row.status)" size="mini">
                                        <i :class="getStatusIcon(scope.row.status)"></i>
                                        {{ getLogStatusText(scope.row.status) }}
                                    </el-tag>
                                </template>
                            </el-table-column>

                            <el-table-column prop="amount" label="交易金额" width="120">
                                <template slot-scope="scope">
                                    <div v-if="scope.row.amount" class="amount-cell">
                                        <span class="amount">{{ formatNumber(scope.row.amount) }}</span>
                                        <span class="currency">{{ scope.row.currency }}</span>
                                    </div>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column label="错误信息" min-width="120" show-overflow-tooltip>
                                <template slot-scope="scope">
                                    <div v-if="scope.row.error_message" class="error-cell">
                                        <el-tooltip :content="scope.row.error_message" placement="top">
                                            <div class="error-content">
                                                <i class="el-icon-warning-outline"></i>
                                                <span>{{ scope.row.error_message }}</span>
                                            </div>
                                        </el-tooltip>
                                    </div>
                                    <div v-else class="success-cell">
                                        <i class="el-icon-circle-check"></i>
                                        <span>正常</span>
                                    </div>
                                </template>
                            </el-table-column>

                            <el-table-column label="付款账号" width="140">
                                <template slot-scope="scope">
                                    <div v-if="scope.row.from_account" class="account-cell">
                                        <i class="el-icon-wallet"></i>
                                        <span>{{ scope.row.from_account }}</span>
                                    </div>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column label="收款账号" width="140">
                                <template slot-scope="scope">
                                    <div v-if="scope.row.to_account" class="account-cell">
                                        <i class="el-icon-bank-card"></i>
                                        <span>{{ scope.row.to_account }}</span>
                                    </div>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column prop="to_account_name" label="收款人" width="120" show-overflow-tooltip>
                                <template slot-scope="scope">
                                    <span v-if="scope.row.to_account_name">{{ scope.row.to_account_name }}</span>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column prop="transaction_id" label="交易流水号" width="200" show-overflow-tooltip>
                                <template slot-scope="scope">
                                    <div v-if="scope.row.transaction_id" class="transaction-cell">
                                        <span>{{ scope.row.transaction_id }}</span>
                                        <el-button
                                            type="text"
                                            size="mini"
                                            @click="copyText(scope.row.transaction_id)"
                                            style="margin-left: 5px;">
                                            <i class="el-icon-document-copy"></i>
                                        </el-button>
                                    </div>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column label="账户余额变化" width="160">
                                <template slot-scope="scope">
                                    <div v-if="scope.row.before_balance !== null && scope.row.after_balance !== null" class="balance-cell">
                                        <div class="balance-before">
                                            <span class="label">前:</span>
                                            <span class="value">{{ formatNumber(scope.row.before_balance) }}</span>
                                        </div>
                                        <div class="balance-after">
                                            <span class="label">后:</span>
                                            <span class="value">{{ formatNumber(scope.row.after_balance) }}</span>
                                        </div>
                                        <div class="balance-diff" :class="getBalanceDiffClass(scope.row)">
                                            <i :class="getBalanceDiffIcon(scope.row)"></i>
                                            <span>{{ formatBalanceDiff(scope.row) }}</span>
                                        </div>
                                    </div>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column prop="process_time" label="处理耗时" width="100">
                                <template slot-scope="scope">
                                    <div v-if="scope.row.process_time" class="process-time-cell">
                                        <i class="el-icon-timer"></i>
                                        <span>{{ formatProcessTime(scope.row.process_time) }}</span>
                                    </div>
                                    <span v-else class="no-data">-</span>
                                </template>
                            </el-table-column>

                            <el-table-column prop="retry_count" label="重试次数" width="80">
                                <template slot-scope="scope">
                                    <el-badge
                                        :value="scope.row.retry_count"
                                        :type="scope.row.retry_count > 0 ? 'warning' : 'info'"
                                        :hidden="scope.row.retry_count === 0">
                                        <span>{{ scope.row.retry_count || 0 }}</span>
                                    </el-badge>
                                </template>
                            </el-table-column>

                        </el-table>
                    </div>
                </el-tab-pane>
            </el-tabs>

            <div slot="footer" class="dialog-footer">
                <el-button @click="dialogVisible = false">关闭</el-button>
                <el-button
                    type="primary"
                    @click="refreshLogs"
                    :loading="logsLoading"
                    v-if="operationLogs.length > 0">
                    <i class="el-icon-refresh"></i>
                    刷新记录
                </el-button>
            </div>
        </el-dialog>

        <el-dialog :visible.sync="settingCoolDownBool" title="冷静期时间设置" width="30%">
            <div class="time-piker-box">
                <el-time-picker
                    value-format="mm:ss"
                    align="center"
                    format="mm:ss"
                    :disabled-hours="true"
                    v-model="settingCoolDownForm.time"
                    placeholder=""></el-time-picker>
            </div>
            <div slot="footer" class="dialog-footer">
                <el-button @click="settingCoolDownBool = false">关闭</el-button>
                <el-button type="primary" @click="settingCoolDownSubmit">确认</el-button>
            </div>
        </el-dialog>
        <el-dialog :visible.sync="settingOrderCoolDownBool" title="订单冷静期时间设置" width="40%">
            <div class="time-piker-box">
                <el-form :model="levelsCoolDownForm" ref="dynamicValidateForm" label-width="130px" class="demo-dynamic">
                    <el-form-item
                        v-for="(domain, index) in levelsCoolDownForm.levelsCoolDown"
                        :label="'等级' + (index + 1) + '(分钟)'"
                        :key="domain.key"
                        :rules="{
                          required: true, message: '等级分钟数不能为空', trigger: 'blur'
                        }"
                    >
                        <el-input-number :step="1" :min="1" :step-strictly="true" v-model="domain.minutes">
                        </el-input-number>
                        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<el-button type="danger" :loading="orderCoolDownLoading" @click.prevent="removeDomain(domain)">删除</el-button>
                    </el-form-item>
                    <el-form-item>
                        <el-button :loading="orderCoolDownLoading" @click="addDomain">新增等级</el-button>
                        <el-button :loading="orderCoolDownLoading" @click="resetForm">重置</el-button>
                    </el-form-item>
                </el-form>
            </div>
            <div slot="footer" class="dialog-footer">
                <el-button @click="settingOrderCoolDownBool = false">关闭</el-button>
                <el-button type="primary" @click="submitForm('dynamicValidateForm')">确认</el-button>
            </div>
        </el-dialog>
    </div>
</template>

<script>
import { deepClone } from '@/utils'
import {
    getAutoPaymentStats,
    getAutoPaymentOrders,
    toggleAutoPayment,
    getAutoPaymentToggleStatus,
    emergencyStopAutoPayment,
    getAutoPaymentMonitor,
    getAutoPaymentOrderDetail, paymentIdCooldown, setPaymentIdCooldown, orderCooldownConfig, setOrderCooldownConfig
} from '@/api/order'

export default {
    name: 'AutoDfddMonitor',
    data() {
        return {
            settingCoolDownForm:{
                time: '00:00',
            },
            coolDownTimer:{},
            settingCoolDownBool:false,
            orderCoolDownLoading:false,
            settingOrderCoolDownBool:false,
            levelsCoolDownForm:{
                levelsCoolDown:[],
            },
            autoPaymentEnabled: true, // 自动代付开关
            emergencyLoading: false, // 紧急停止加载状态
            monitorList: [], // 监控数据列表
            dialogData: {}, // 详情对话框数据
            dialogVisible: false,
            activeTab: 'basic',           // 当前选中的Tab
            operationLogs: [],            // 操作日志数据
            logsLoading: false,           // 日志加载状态
            // 统计数据
            stats: {
                todayAmount: 1250000,
                todayGrowth: 25,
                todayCount: 2500,
                todayCountGrowth: 10,
                yesterdayAmount: 1000000,
                yesterdayCount: 2200,
                totalAmount: 123456789,
                totalDailyIncrease: 250000,
                totalCount: 250000,
                totalCountIncrease: 250000,
                successRate: 98.5,
                successRateIncrease: 0.5
            },
            // 搜索参数
            searchParams: {
                orderCode: '',
                merchantId: '',
                startDate: '',
                endDate: ''
            },
            paginationData: { // 翻页信息
                page: 1,
                size: 10,
                total: 0
            }
        }
    },
    async created() {
        await this.getToggleStatus()
        await this.getStats()
        await this.getData()

        // 启动自动刷新
        this.startAutoRefresh()
    },
    beforeDestroy() {
        if (this.timer) {
            clearInterval(this.timer)
        }
    },
    mounted() {
        this.getPaymentIdCooldown()
    },
    activated(){
        this.getPaymentIdCooldown()
    },
    methods: {
        submitForm(formName) {
            this.$refs[formName].validate(async (valid) => {
                if (valid) {
                    this.orderCoolDownLoading = true
                    let submitArr = [...this.levelsCoolDownForm.levelsCoolDown].map((item,index)=>{
                        return {
                            level:index + 1,
                            minutes:item.minutes
                        }
                    })
                    try {
                        const res = await setOrderCooldownConfig({
                            levels:submitArr
                        })
                        this.orderCoolDownLoading = false
                        if (res.code == 20000){
                            this.$message.success('success')
                            this.settingOrderCoolDownBool = false
                        }
                    }catch(err){
                        this.orderCoolDownLoading = false
                    }
                } else {
                    console.log('error submit!!');
                    return false;
                }
            });
        },
        async resetForm() {
            this.orderCoolDownLoading = true
            try{
                const res = await orderCooldownConfig()
                this.levelsCoolDownForm.levelsCoolDown = res.data.levels
                this.orderCoolDownLoading = false
            }catch (e) {
                this.orderCoolDownLoading = false
            }
        },
        removeDomain(item) {
            var index = this.levelsCoolDownForm.levelsCoolDown.indexOf(item)
            if (index !== -1) {
                this.levelsCoolDownForm.levelsCoolDown.splice(index, 1)
            }
        },
        addDomain() {
            this.levelsCoolDownForm.levelsCoolDown.push({
                minutes: '',
            });
        },
        coolDownSetting(){
            this.settingCoolDownBool = true
        },
        async orderCoolDownSetting(){
            try {
                this.orderCoolDownLoading = true
                const res = await orderCooldownConfig()
                this.orderCoolDownLoading = false
                this.levelsCoolDownForm.levelsCoolDown = res.data.levels
                this.settingOrderCoolDownBool = true
            }catch (e) {
                this.orderCoolDownLoading = false
            }
        },
        async settingCoolDownSubmit(){
            let timeArr = this.settingCoolDownForm.time.split(":")
            if (timeArr[0]*1 === 0 && timeArr[1]*1 < 30){
                this.$message.warning("最小冷静期为30秒！")
                return
            }
            const res = await setPaymentIdCooldown({
                minutes: timeArr[0] * 1,
                seconds: timeArr[1] * 1
            })
            if (res.code == 20000){
                this.$message.success('设置成功！')
                this.settingCoolDownBool = false
                this.getPaymentIdCooldown()
                this.settingCoolDownForm.time = new Date(2016, 9, 10, 0, 0);
            }
        },

        /* 格式化数字 */
        formatNumber(num) {
            if (!num) return '0'
            return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
        },
        async getPaymentIdCooldown(){
            const res = await paymentIdCooldown()
            res.data.minutes = res.data.minutes * 1 > 9?res.data.minutes:'0' + res.data.minutes;
            res.data.seconds = res.data.seconds * 1 > 9?res.data.seconds:'0' + res.data.seconds;
            this.coolDownTimer = res.data
        },
        /* 自动开关变化 */
        async handleSwitchChange(value) {
            try {
                const res = await toggleAutoPayment({ enabled: value })
                if (res.code === 20000) {
                    this.$message.success(value ? '自动代付已开启' : '自动代付已关闭')
                } else {
                    throw new Error(res.message || '操作失败')
                }
            } catch (error) {
                this.$message.error(error.message || '操作失败')
                // 恢复开关状态
                this.autoPaymentEnabled = !value
            }
        },

        /* 搜索 */
        handleSearch() {
            // 添加查询提示
            this.$message.info('正在查询...')
            console.log('查询参数:', this.searchParams)

            this.paginationData.page = 1
            this.getData()

            // 查询时停止自动刷新，避免覆盖查询结果
            if (this.timer) {
                clearInterval(this.timer)
                this.timer = null
                console.log('已停止自动刷新')
            }
        },

        /* 重置搜索 */
        handleReset() {
            this.searchParams = {
                orderCode: '',
                merchantId: '',
                startDate: '',
                endDate: ''
            }
            this.paginationData.page = 1
            this.getData()

            // 重置后恢复自动刷新
            this.startAutoRefresh()
        },

        /* 紧急停止 */
        async handleEmergencyStop() {
            this.$confirm('确认要紧急停止所有自动代付操作吗？', '警告', {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                type: 'warning'
            }).then(async () => {
                this.emergencyLoading = true
                try {
                    const res = await emergencyStopAutoPayment()
                    if (res.code === 20000) {
                        this.$message.success('紧急停止操作已执行')
                        this.autoPaymentEnabled = false
                        this.getData()
                    } else {
                        throw new Error(res.message || '紧急停止失败')
                    }
                } catch (error) {
                    this.$message.error(error.message || '紧急停止失败')
                } finally {
                    this.emergencyLoading = false
                }
            })
        },

        /* 获取数据*/
        async getData() {
            try {
                const params = {
                    ...this.searchParams,
                    page: this.paginationData.page,
                    page_size: this.paginationData.size
                }

                const res = await getAutoPaymentOrders(params)
                if (res.code === 20000) {
                    // 添加防御性编程，检查数据结构
                    if (res.data && Array.isArray(res.data.list)) {
                        this.monitorList = res.data.list.map(item => {
                            // 确保item存在
                            if (!item) {
                                console.warn('订单列表中发现空数据项')
                                return null
                            }

                            return {
                                orderCode: item.order_code || '',
                                merchantId: item.merchant_id || '',
                                amount: item.amount || 0,
                                lastTime: item.success_time || item.paid_time || item.accept_time || item.created_time || '',
                        status: this.convertStatusToFrontend(item.status),
                        remark: item.remarks || '-',
                                createTime: item.created_time || '',
                        // 保存原始数据用于详情查看
                        _originalData: item
                            }
                        }).filter(item => item !== null) // 过滤掉空数据

                        this.paginationData.total = res.data.total || 0
                    } else {
                        console.error('API返回数据格式错误:', res.data)
                        this.monitorList = []
                        this.paginationData.total = 0
                        this.$message.warning('数据格式错误，请联系管理员')
                    }
                } else {
                    throw new Error(res.message || '获取数据失败')
                }
            } catch (error) {
                this.$message.error(error.message || '获取数据失败')
                console.error(error)
            }
        },

        /* 获取统计数据 */
        async getStats() {
            try {
                const res = await getAutoPaymentStats()
                if (res.code === 20000) {
                    const data = res.data
                    this.stats = {
                        todayAmount: data.today.amount,
                        todayGrowth: this.calculateGrowth(data.today.amount, data.yesterday.amount),
                        todayCount: data.today.count,
                        todayCountGrowth: this.calculateGrowth(data.today.count, data.yesterday.count),
                        yesterdayAmount: data.yesterday.amount,
                        yesterdayCount: data.yesterday.count,
                        totalAmount: data.total.amount,
                        totalDailyIncrease: data.today_all ? data.today_all.amount : data.today.amount,
                        totalCount: data.total.count,
                        totalCountIncrease: data.today_all ? data.today_all.count : data.today.count,
                        successRate: data.success_rate,
                        successRateIncrease: this.calculateGrowth(data.today_success_rate || 0, data.yesterday_success_rate || 0)
                    }
                }
            } catch (error) {
                console.error('获取统计数据失败:', error)
            }
        },

        /* 获取开关状态 */
        async getToggleStatus() {
            try {
                const res = await getAutoPaymentToggleStatus()
                if (res.code === 20000) {
                    this.autoPaymentEnabled = res.data.enabled
                }
            } catch (error) {
                console.error('获取开关状态失败:', error)
            }
        },

        /* 计算增长率 */
        calculateGrowth(current, previous) {
            if (previous === 0) return current > 0 ? 100 : 0
            return ((current - previous) / previous * 100).toFixed(1)
        },

        /* 转换后端状态到前端显示 */
        convertStatusToFrontend(backendStatus) {
            if (backendStatus === null || backendStatus === undefined) {
                return 'processing'
            }

            const statusMap = {
                '0': 'pending',
                '1': 'processing',
                '2': 'confirming',
                '3': 'completed',
                '4': 'notified',
                '5': 'exception_success',
                '-1': 'failed'
            }
            return statusMap[backendStatus] || 'processing'
        },

        /* 生成模拟数据 */
        generateMockData() {
            const statusOptions = ['processing', 'completed', 'failed']
            const statusTexts = ['处理中', '接口通过', '失效']
            const merchantIds = ['MS1001', 'MS1002', 'MS1003']

            const data = []
            for (let i = 1; i <= 3; i++) {
                const status = statusOptions[i - 1]
                data.push({
                    orderCode: `K2025081${10000 + i}`,
                    merchantId: merchantIds[i - 1],
                    amount: i === 1 ? 50000 : i === 2 ? 120000 : 30000,
                    lastTime: `2025-08-11 09:${12 + i}:${30 + i}`,
                    status: status,
                    remark: i === 1 ? '已成功第三方' : i === 2 ? '等待第三方等待第三方' : '备注不定',
                    createTime: `2025-08-11 09:${12 + i}:${30 + i}`
                })
            }

            return {
                data: data,
                total: 3
            }
        },

        /* 获取状态类型 */
        getStatusType(status) {
            // 处理 null、undefined 或其他无效值
            if (status === null || status === undefined) {
                return 'info'
            }

            const typeMap = {
                'pending':'primary',
                'processing': 'warning',
                'confirming': 'danger',
                'completed': 'success',
                'notified': 'info',
                'exception_success': 'warning',
                'failed': 'danger'
            }
            return typeMap[status] || 'info'
        },

        /* 获取状态文本 */
        getStatusText(status) {
            // 处理 null、undefined 或其他无效值
            if (status === null || status === undefined) {
                return '未知'
            }

            const textMap = {
                'pending':'待处理',
                'processing': '处理中',
                'confirming': '待确认',
                'completed': '成功',
                'notified': '通知商户已到账',
                'exception_success': '异常按成功',
                'failed': '失败'
            }
            return textMap[status] || '未知'
        },


        /* 查看详情 */
        async viewDetails(scope) {
            try {
                this.dialogData = deepClone(scope.row)
                this.dialogVisible = true
                this.activeTab = 'basic'

                // 获取交易记录
                await this.getOperationLogs(scope.row.orderCode)
            } catch (error) {
                console.error('详情显示失败:', error)
                this.$message.error('详情显示失败: ' + error.message)
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

        /* 启动自动刷新 */
        startAutoRefresh() {
            // 清除existing timer
            if (this.timer) {
                clearInterval(this.timer)
            }

            // 只有在没有查询条件时才自动刷新
            const hasSearchConditions = this.searchParams.orderCode ||
                                       this.searchParams.merchantId ||
                                       this.searchParams.startDate ||
                                       this.searchParams.endDate

            if (!hasSearchConditions) {
                this.timer = setInterval(() => {
                    this.getStats()
                    this.getData()
                }, 30000) // 每30秒刷新一次
            }
        },

        /* 获取交易记录 */
        async getOperationLogs(orderCode) {
            this.logsLoading = true

            try {
                const res = await getAutoPaymentOrderDetail({ orderCode })

                if (res.code === 20000) {
                    this.operationLogs = res.data.operation_logs || []

                    // 如果有交易记录，自动切换到交易记录Tab
                    if (this.operationLogs.length > 0 && this.activeTab === 'basic') {
                        this.$nextTick(() => {
                            this.activeTab = 'logs'
                        })
                    }
                } else {
                    this.$message.warning('获取交易记录失败: ' + (res.message || '未知错误'))
                    this.operationLogs = []
                }
            } catch (error) {
                console.error('获取交易记录失败:', error)
                this.$message.error('网络错误: ' + error.message)
                this.operationLogs = []
            } finally {
                this.logsLoading = false
            }
        },

        /* 刷新交易记录 */
        async refreshLogs() {
            if (this.dialogData.orderCode) {
                await this.getOperationLogs(this.dialogData.orderCode)
                this.$message.success('交易记录已刷新')
            }
        },

                /* 获取操作类型标签样式 */
        getOperationTypeTag(type) {
            // 处理 null、undefined 或其他无效值
            if (type === null || type === undefined) {
                return 'info'
            }

            const tagMap = {
                'transfer': 'primary',
                'balance_check': 'info',
                'login': 'success',
                'error': 'danger',
                'payment': 'warning'
            }
            return tagMap[type] || 'info'
        },

        /* 获取操作类型文本 */
        getOperationTypeText(type) {
            // 处理 null、undefined 或其他无效值
            if (type === null || type === undefined) {
                return '未知'
            }

            const textMap = {
                'transfer': '转账',
                'balance_check': '余额查询',
                'login': '登录',
                'error': '错误处理',
                'payment': '代付'
            }
            return textMap[type] || type
        },

        /* 获取日志状态文本 */
        getLogStatusText(status) {
            // 处理 null、undefined 或其他无效值
            if (status === null || status === undefined) {
                return '未知'
            }

            const textMap = {
                'success': '成功',
                'failed': '失败',
                'pending': '处理中',
                'processing': '执行中'
            }
            return textMap[status] || status
        },

        /* 获取状态标签样式 */
        getLogStatusTag(status) {
            // 处理 null、undefined 或其他无效值
            if (status === null || status === undefined) {
                return 'info'
            }

            const tagMap = {
                'success': 'success',
                'failed': 'danger',
                'pending': 'warning',
                'processing': 'primary'
            }
            return tagMap[status] || 'info'
        },

        /* 获取状态图标 */
        getStatusIcon(status) {
            // 处理 null、undefined 或其他无效值
            if (status === null || status === undefined) {
                return 'el-icon-info'
            }

            const iconMap = {
                'success': 'el-icon-circle-check',
                'failed': 'el-icon-circle-close',
                'pending': 'el-icon-warning',
                'processing': 'el-icon-loading'
            }
            return iconMap[status] || 'el-icon-info'
        },

        /* 格式化处理时间 */
        formatProcessTime(time) {
            if (time < 1) {
                return `${(time * 1000).toFixed(0)}ms`
            } else {
                return `${time.toFixed(2)}s`
            }
        },

        /* 复制文本 */
        copyText(text) {
            navigator.clipboard.writeText(text).then(() => {
                this.$message.success('已复制到剪贴板')
            }).catch(() => {
                this.$message.error('复制失败')
            })
        },

        /* 获取余额变化样式类 */
        getBalanceDiffClass(row) {
            const diff = row.after_balance - row.before_balance
            if (diff > 0) return 'balance-increase'
            if (diff < 0) return 'balance-decrease'
            return 'balance-same'
        },

        /* 获取余额变化图标 */
        getBalanceDiffIcon(row) {
            const diff = row.after_balance - row.before_balance
            if (diff > 0) return 'el-icon-top'
            if (diff < 0) return 'el-icon-bottom'
            return 'el-icon-minus'
        },

        /* 格式化余额变化 */
        formatBalanceDiff(row) {
            const diff = row.after_balance - row.before_balance
            if (diff === 0) return '无变化'
            const sign = diff > 0 ? '+' : ''
            return `${sign}${this.formatNumber(diff)}`
        }
    }
}
</script>

<style lang="scss" scoped>
.app-container {
    padding: 20px;
    background-color: #f5f5f5;
    min-height: 100vh;
}

// 顶部标题区域
.header-section {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;

    .page-title {
        margin: 0;
        font-size: 24px;
        font-weight: bold;
        color: #333;
    }

    .auto-switch {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        font-size: 14px;
        color: #666;
        width: 150px;
        .switch-box{
            width: 150px;
        }
        .cool-down-box{
            width: 150px;
            font-size: 15px;
            cursor: pointer;
        }
    }
}

// 统计卡片区域
.stats-section {
    margin-bottom: 30px;

    .stat-card {
        background: white;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
        display: flex;
        align-items: center;
        height: 100px;

        .stat-icon {
            width: 60px;
            height: 60px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 15px;

            i {
                font-size: 24px;
                color: white;
            }

            &.blue {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }

            &.yellow {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            }

            &.gray {
                background: linear-gradient(135deg, #4b6cb7 0%, #182848 100%);
            }

            &.green {
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            }

            &.purple {
                background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
            }
        }

        .stat-content {
            flex: 1;

            .stat-title {
                font-size: 14px;
                color: #999;
                margin-bottom: 8px;
            }

            .stat-value {
                font-size: 24px;
                font-weight: bold;
                color: #333;
                margin-bottom: 5px;
            }

            .stat-trend {
                font-size: 12px;

                &.positive {
                    color: #67c23a;
                }

                i {
                    margin-right: 4px;
                }
            }

            .stat-desc {
                font-size: 12px;
                color: #999;
            }
        }
    }
}

// 搜索区域
.search-section {
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
    margin-bottom: 20px;
}

// 表格区域
.table-section {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
    padding: 0;
    overflow: hidden;
}

// 分页区域
.pagination-section {
    margin-top: 20px;
    text-align: center;
}

// 紧急停止按钮区域
.emergency-section {
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 1000;

    .el-button {
        border-radius: 50px;
        padding: 15px 30px;
        font-size: 16px;
        font-weight: bold;
        box-shadow: 0 4px 20px rgba(245, 108, 108, 0.3);

        &:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 25px rgba(245, 108, 108, 0.4);
        }
    }
}

// 表格样式调整
::v-deep .el-table {
    .el-table__header {
        th {
            background-color: #f8f9fa !important;
            color: #495057 !important;
            font-weight: 600;
        }
    }

    .el-table__row {
        &:hover {
            background-color: #f8f9fa;
        }
    }
}

// 响应式设计
@media (max-width: 768px) {
    .header-section {
        flex-direction: column;
        align-items: flex-start;
        gap: 15px;
    }

    .search-section {
        .el-row {
            .el-col {
                margin-bottom: 10px;
            }
        }
    }

    .emergency-section {
        bottom: 20px;
        right: 20px;

        .el-button {
            padding: 12px 24px;
            font-size: 14px;
        }
    }
}

// 交易记录相关样式
.logs-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
}

.logs-summary {
    display: flex;
    align-items: center;
}

.no-logs {
    text-align: center;
    padding: 60px 0;
}

.no-data {
    color: #c0c4cc;
    font-style: italic;
}

.time-cell {
    display: flex;
    align-items: center;
    font-size: 12px;
}

.time-cell i {
    margin-right: 5px;
    color: #909399;
}

.amount-cell {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}

.amount {
    font-weight: bold;
    color: #409eff;
}

.currency {
    font-size: 11px;
    color: #909399;
}

.account-cell {
    display: flex;
    align-items: center;
    font-size: 12px;
}

.account-cell i {
    margin-right: 5px;
    color: #67c23a;
}

.transaction-cell {
    display: flex;
    align-items: center;
}

.balance-cell {
    font-size: 12px;
}

.balance-before, .balance-after {
    display: flex;
    justify-content: space-between;
    margin: 1px 0;
}

.balance-diff {
    display: flex;
    align-items: center;
    margin-top: 3px;
    font-weight: bold;
    font-size: 11px;
}

.balance-increase {
    color: #67c23a;
}

.balance-decrease {
    color: #f56c6c;
}

.balance-same {
    color: #909399;
}

.label {
    color: #909399;
    margin-right: 5px;
}

.value {
    font-weight: 500;
}

.process-time-cell {
    display: flex;
    align-items: center;
    font-size: 12px;
}

.process-time-cell i {
    margin-right: 3px;
    color: #409eff;
}

.error-cell {
    color: #f56c6c;
}

.error-content {
    display: flex;
    align-items: center;
}

.error-content i {
    margin-right: 5px;
}

.success-cell {
    color: #67c23a;
    display: flex;
    align-items: center;
}

.success-cell i {
    margin-right: 5px;
}

.trace-id {
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: #909399;
}

.dialog-footer {
    text-align: right;
    border-top: 1px solid #e4e7ed;
    padding-top: 15px;
}

</style>
<style>
