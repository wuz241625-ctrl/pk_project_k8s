<template>
  <el-row :gutter="40" class="panel-group">
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('count')">
        <div class="card-panel-icon-wrapper icon-default">
          <svg-icon icon-class="chart" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('order_total') }}
          </div>
          <count-to :start-val="0" :end-val="alldata.count?alldata.count:0" :duration="600" class="card-panel-num" />
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('count_s')">
        <div class="card-panel-icon-wrapper icon-success">
          <svg-icon icon-class="chart" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('successful_orders') }}
          </div>
          <count-to :start-val="0" :end-val="alldata.count_s?alldata.count_s:0" :duration="800" class="card-panel-num" />
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('count_f')">
        <div class="card-panel-icon-wrapper icon-fail">
          <svg-icon icon-class="chart" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('failed_orders') }}
          </div>
          <count-to :start-val="0" :end-val="alldata.count_f?alldata.count_f:0" :duration="1000" class="card-panel-num" />
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('rate')">
        <div class="card-panel-icon-wrapper icon-default">
          <svg-icon icon-class="dashboard" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('success_rate') }}
          </div>
          <count-to :start-val="0" :end-val="alldata.rate?alldata.rate:0" :duration="1200" class="card-panel-num" />%
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('amount')">
        <div class="card-panel-icon-wrapper icon-default">
          <svg-icon icon-class="money" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('transaction_amount') }}
          </div>
          <count-to :start-val="0" :end-val="parseFloat(alldata.amount)?parseFloat(alldata.amount):0" :duration="600" :decimals="4" class="card-panel-num" />
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('amount_s')">
        <div class="card-panel-icon-wrapper icon-success">
          <svg-icon icon-class="money" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('successful_amount') }}
          </div>
          <count-to :start-val="0" :end-val="parseFloat(alldata.amount_s)?parseFloat(alldata.amount_s):0" :duration="800" :decimals="4" class="card-panel-num" />
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('amount_f')">
        <div class="card-panel-icon-wrapper icon-fail">
          <svg-icon icon-class="money" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('failed_amount') }}
          </div>
          <count-to :start-val="0" :end-val="alldata.amount_f?parseFloat(alldata.amount_f):0" :duration="1000" :decimals="4" class="card-panel-num" />
        </div>
      </div>
    </el-col>
    <el-col :xs="12" :sm="12" :lg="6" class="card-panel-col">
      <div class="card-panel" @click="handleSetLineChartData('poundage')">
        <div class="card-panel-icon-wrapper icon-default">
          <svg-icon icon-class="star" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('commission') }}
          </div>
          <count-to :start-val="0" :end-val="parseFloat(alldata.poundage)?parseFloat(alldata.poundage):0" :duration="1200" :decimals="4" class="card-panel-num" />
        </div>
      </div>
    </el-col>
        <el-col :xs="12" :sm="12" :lg="8" class="card-panel-col">
      <div class="card-panel">
        <div class="card-panel-icon-wrapper icon-success">
          <svg-icon icon-class="money" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('merchant_balance') }}
          </div>
          <count-to :start-val="0" :end-val="parseFloat(alldata.balance)?parseFloat(alldata.balance):0" :duration="1200" :decimals="4" class="card-panel-num" />
        </div>
      </div>
    </el-col>
        <el-col :xs="12" :sm="12" :lg="8" class="card-panel-col">
      <div class="card-panel">
        <div class="card-panel-icon-wrapper icon-fail">
          <svg-icon icon-class="money" class-name="card-panel-icon" />
        </div>
        <div class="card-panel-description">
          <div class="card-panel-text">
            {{ $t('frozen_balance') }}
          </div>
          <count-to :start-val="0" :end-val="parseFloat(alldata.balance_frozen)?parseFloat(alldata.balance_frozen):0" :duration="1200" :decimals="4" class="card-panel-num" />
        </div>
      </div>
    </el-col>
  </el-row>
</template>

<script>
import CountTo from 'vue-count-to'

export default {
    components: {
        CountTo
    },
    props: {
        alldata: {
            type: Object,
            required: true
        }
    },
    methods: {
        handleSetLineChartData(type) {
            this.$emit('handleSetLineChartData', type)
        }
    }
}
</script>

<style lang="scss" scoped>
.panel-group {
  margin-top: 18px;

  .card-panel-col {
    margin-bottom: 32px;
  }

  .card-panel {
    height: 108px;
    cursor: pointer;
    font-size: 12px;
    position: relative;
    overflow: hidden;
    color: #666;
    background: #fff;
    box-shadow: 4px 4px 40px rgba(0, 0, 0, .05);
    border-color: rgba(0, 0, 0, .05);

    &:hover {
      .card-panel-icon-wrapper {
        color: #fff;
      }
      .icon-default {
        background: #36a3f7;
      }

      .icon-success {
        background: #40c9c6;
      }

      .icon-fail {
        background: #f4516c;
      }
    }
    .icon-default{
        color: #36a3f7;
    }

    .icon-success{
        color: #34bfa3;
    }

    .icon-fail{
        color: #f4516c;
    }

    .card-panel-icon-wrapper {
      float: left;
      margin: 14px 0 0 14px;
      padding: 16px;
      transition: all 0.38s ease-out;
      border-radius: 6px;
    }

    .card-panel-icon {
      float: left;
      font-size: 48px;
    }

    .card-panel-description {
      float: right;
      font-weight: bold;
      margin: 26px;
      margin-left: 0px;

      .card-panel-text {
        line-height: 18px;
        color: rgba(0, 0, 0, 0.45);
        font-size: 16px;
        margin-bottom: 12px;
      }

      .card-panel-num {
        font-size: 20px;
      }
    }
  }
}

@media (max-width:550px) {
  .card-panel-description {
    display: none;
  }

  .card-panel-icon-wrapper {
    float: none !important;
    width: 100%;
    height: 100%;
    margin: 0 !important;

    .svg-icon {
      display: block;
      margin: 14px auto !important;
      float: none !important;
    }
  }
}
</style>
