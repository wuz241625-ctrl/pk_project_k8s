<template>
  <div class="dashboard-editor-container">
    <DateTimePicker ref="dateTime" class="DateTimePicker" />
    <el-button type="primary" @click="getData">{{$t('statics')}}</el-button>
    <panel-group :alldata="allData" @handleSetLineChartData="handleSetLineChartData" />

    <el-row style="background:#fff;padding:16px 16px 0;margin-bottom:32px;">
      <line-chart :chart-data="lineChartData" />
    </el-row>
  </div>
</template>

<script>
import DateTimePicker from './components/DateTimePicker.vue'
import PanelGroup from './components/PanelGroup'
import LineChart from './components/LineChart'
import {
    getCount,
    getCountOneW
} from '@/api/count'

export default {
    components: {
        DateTimePicker,
        PanelGroup,
        LineChart
    },
    data() {
        return {
            lineChartDatas: [],
            lineChartData: [0, 0, 0, 0, 0, 0, 0],
            allData: {}
        }
    },
    created() {
        this.getData()
    },
    methods: {
        async handleSetLineChartData(type) {
            // payment-stats 代付  /payment-stats
            // dashboard 代收  /dashboard
            var data = {}
            data.type = this.$route.path === '/dashboard' ? 'ds' : 'df'
            data.datatype = type
            const res = await getCountOneW(data)
            this.lineChartData = res.data
        },
        async getData() {
            var data = {}
            // payment-stats 代付  /payment-stats
            // dashboard 代收  /dashboard
            data.type = this.$route.path === '/dashboard' ? 'ds' : 'df'
            if (this.$refs.dateTime) {
                data.serchData = this.$refs.dateTime.value
            } else {
                data.serchData = [new Date().toLocaleDateString().split('/').join('-') + ' 00:00:00', new Date()
                    .toLocaleString().split('/').join('-')
                ]
            }
            const res = await getCount(data)
            this.allData = res.data
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
