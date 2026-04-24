<template>
    <div class="dashboard-editor-container">
        <el-button type="primary" @click="getData" style="margin-bottom: 10px;">{{ $t('search.refresh') }}</el-button>
        <el-button type="primary" @click="updateRules" style="margin-bottom: 10px;">{{ $t('collectPartner.buttons.updateRules') }}</el-button>
        <el-row style="background:#fff;padding:10px 10px 0;margin-bottom:32px;margin-left: auto">
            <IndefiniteChart :chart-data="indefiniteChartData" @barClick="barClick"/>
<!--            <div class="app-container" v-show="dialogVisible">-->
<!--                <el-table :data="partnerDatas" style="width: 100%" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">-->
<!--                    <el-table-column align="center" :label="$t('method.Mslb.table.id')">-->
<!--                        <template slot-scope="scope">-->
<!--                          {{ scope.row.id }}-->
<!--                        </template>-->
<!--                    </el-table-column>-->
<!--                    <el-table-column align="center" :label="$t('method.Mslb.table.name')">-->
<!--                        <template slot-scope="scope">-->
<!--                          {{ scope.row.name }}-->
<!--                        </template>-->
<!--                    </el-table-column>-->
<!--                    <el-table-column align="center" :label="$t('method.Mslb.table.balance')" sortable>-->
<!--                        <template slot-scope="scope">-->
<!--                          {{ scope.row.balance }}-->
<!--                        </template>-->
<!--                    </el-table-column>-->
<!--                    <el-table-column align="center" :label="$t('method.Mslb.table.actions')" width="220px">-->
<!--                        <template slot-scope="scope">-->
<!--                            <el-button type="primary" size="small" @click="handleCode(scope)">{{ $t('collectPartner.buttons.code') }}</el-button>-->
<!--                        </template>-->
<!--                    </el-table-column>-->
<!--                </el-table>-->
<!--                <div class="block" style="margin-top: 20px;">-->
<!--                    <el-pagination-->
<!--                        background-->
<!--                        :current-page="paginationData.page"-->
<!--                        :page-sizes="[10, 20, 50, 100]"-->
<!--                        :page-size="paginationData.size"-->
<!--                        layout="total, sizes, prev, pager, next, jumper"-->
<!--                        :total="paginationData.total"-->
<!--                        @size-change="handleSizeChange"-->
<!--                        @current-change="handleCurrentChange"-->
<!--                    />-->
<!--                </div>-->
<!--            </div>-->
        </el-row>

<!--        <el-dialog :visible.sync="dialogVisible2" :title="$t('collectPartner.buttons.code')">-->
<!--            <el-table :data="codeInfos" style="width: 100%" border stripe :header-cell-style="{background:'#DCDFE6', color:'#606266'}">-->
<!--                <el-table-column align="center" :label="$t('method.payment01.ds.table.id')">-->
<!--                    <template slot-scope="scope">-->
<!--                      {{ scope.row.id }}-->
<!--                    </template>-->
<!--                </el-table-column>-->
<!--                <el-table-column align="center" :label="$t('method.payment01.ds.table.upi')">-->
<!--                    <template slot-scope="scope">-->
<!--                      {{ scope.row.upi }}-->
<!--                    </template>-->
<!--                </el-table-column>-->
<!--           </el-table>-->
<!--        </el-dialog>-->

        <el-dialog :visible.sync="dialogVisible3" :title="$t('collectPartner.buttons.updateRules')">
            <el-form :model="filtersData" label-width="180px">
                <el-form-item :label="$t('collectPartner.filtersDataForm.bound')">
                    <el-input v-model="filtersData.bound" />
                </el-form-item>
                <el-form-item :label="$t('collectPartner.filtersDataForm.num')">
                    <el-input v-model="filtersData.num"/>
                </el-form-item>
                <el-form-item :label="$t('collectPartner.filtersDataForm.data_select')">
                    <el-input v-model="filtersData.data_select"/>
                </el-form-item>
                <el-form-item :label="$t('collectPartner.filtersDataForm.interval_time')">
                    <el-input v-model="filtersData.interval_time"/>
                </el-form-item>
            </el-form>
            <h5 v-text="$t('collectPartner.filtersDataForm.rules')" style="margin-left: 120px; color: #d2382f"/>
            <div style="text-align:right;">
                <el-button type="primary" @click="dialogVisibleMigrate">{{ $t('method.Mslb.buttons.cancel') }}</el-button>
                <el-button type="danger" @click="confirmMigration">{{ $t('method.Mslb.buttons.confirm') }}</el-button>
            </div>
        </el-dialog>
    </div>
</template>

<script>
import IndefiniteChart from './components/IndefiniteChart.vue'

import {
    getCollectPartner,
} from '@/api/count'

import {
    getFilters,
    filtersAddOrUpdate
} from '@/api/setting'
import {addPayment} from "@/api/partner";

export default {
    name: 'cf',
    components: {
        IndefiniteChart
    },
    data() {
        return {
            // partnerDatas: [],
            // codeInfos: [],
            filtersData: {},
            // dialogVisible: false,
            // dialogVisible2: false,
            dialogVisible3: false,
            // collect_index: null,
            // id_index: null,
            indefiniteChartData: {
                legend: {
                  selectedMode: false
                },
                grid: {
                      left: 100,
                      right: 100,
                      top: 50,
                      bottom: 50
                },
                yAxis: {
                  type: 'value'
                },
                xAxis: {
                  type: 'category',
                  data: []
                },
                series: [
                   //  {
                   //      name: 'Direct',
                   //      type: 'bar',
                   //      stack: 'total',
                   //      barWidth: '60%',
                   //      label: {
                   //        show: true,
                   //      },
                   //      data: [展示数据]
                   //  },
                   // {
                   //      name: 'Mail Ad',
                   //      type: 'bar',
                   //      stack: 'total',
                   //      barWidth: '60%',
                   //      label: {
                   //        show: true,
                   //      },
                   //      data: []
                   //  }
                ]
            },
            // paginationData: { // 翻页信息
            //     page: 1,
            //     size: 10,
            //     total: 200
            // }
        }
    },
    created() {
        this.getData()
    },
    methods: {
        async getData() {
            this.dialogVisible = false
            let data = {}
            const res = await getCollectPartner(data)
            let result = res.data
            if(result && result.length>0){
                let xAxisData = []
                let sum = []
                let boundData = result[0].bound.split(",")
                for (let j=0;j<result.length;j++){
                    xAxisData[j] = result[j].time
                    let dataSum = 0
                    for(let i=0;i<boundData.length;i++){
                        dataSum += result[j].data[i+""]
                    }
                    sum[j] = dataSum
                }
                let series = []
                for (let i=0;i<boundData.length;i++){
                    let seriesName = ""
                    if(i+1<boundData.length){
                        seriesName = "LV"+i+"("+boundData[i]+"-"+boundData[i+1]+")"
                    }else {
                        seriesName = "LV"+i+"("+boundData[i]+"+)"
                    }
                    let seriesDate = []
                    for (let j=0;j<result.length;j++){
                        if(result[j].data[i+""]){
                            seriesDate[j] = result[j].data[i+""]
                        }else {
                          seriesDate[j] = 0
                        }
                    }
                    series[i] ={
                        name: seriesName,
                        type: 'bar',
                        stack: 'total',
                        barWidth: '20%',
                        label: {
                          show: true,
                          color: "black",
                        },
                        data: seriesDate
                    }
                }
                series.push({
                        name: "Summary",
                        type: 'scatter',
                        // stack: 'total',
                        barWidth: '20%',
                        label: {
                          show: true,
                          color: "black",
                          position: 'top',
                        },
                        data: sum
                    })
                this.indefiniteChartData.xAxis.data = xAxisData
                this.indefiniteChartData.series = series
            }
        },
        /* 改变分页大小 */
        // handleSizeChange(val) {
        //     this.paginationData.size = val
        //     this.getFartner()
        // },
        // /* 改变当前页 */
        // handleCurrentChange(val) {
        //     this.paginationData.page = val
        //     this.getFartner()
        // },
        barClick(data){
            // this.paginationData.total = 0
            // this.paginationData.size = 10
            // this.paginationData.page = 1
            // this.collect_index=data.dataIndex
            // this.id_index=data.seriesIndex
            // this.getFartner()
        },
        // async getFartner(){
        //     let data = {}
        //     data.size = this.paginationData.size
        //     data.page = this.paginationData.page
        //     data.collect_index = this.collect_index
        //     data.id_index = this.id_index
        //     const res = await getPartner(data)
        //     this.partnerDatas =  res.data
        //     this.paginationData.total = res.total
        //     this.dialogVisible = true
        // },
        // async handleCode(data){
        //     const res = await getOnlinePayment({"partner_id": data.row.id})
        //     this.codeInfos = res.data
        //     this.dialogVisible2 = true
        // },
        async dialogVisibleMigrate(){
            this.filtersData = {};
            this.dialogVisible3 = false;
        },
        async confirmMigration(){
            try {
              await filtersAddOrUpdate(this.filtersData)
            } catch (err) {
                return
            }
            this.dialogVisible3 = false
            this.$notify({
                title: this.$t('method.edit.save_success_title'),
                dangerouslyUseHTMLString: true,
                message: this.$t('method.edit.save_success_message'),
                type: 'success'
            })
        },
        async updateRules(){
            const res = await getFilters({"type": 0})
            if(res.data){
                this.filtersData = res.data[0]
                this.dialogVisible3 = true
            }
        }
    }
}
</script>

<style lang="scss" scoped>
    .dashboard-editor-container {
        padding: 32px;
        background-color: rgb(240, 242, 245);
        position: relative;

        .github-corner {
            position: absolute;
            top: 0px;
            border: 0;
            right: 0;
        }

        .chart-wrapper {
            background: #fff;
            padding: 16px 16px 0;
            margin-bottom: 32px;
        }

        .DateTimePicker {
            right: 16px;
        }
    }

    @media (max-width:1024px) {
        .chart-wrapper {
            padding: 8px;
        }
    }
</style>
