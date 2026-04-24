<template>
  <el-date-picker
    v-model="value"
    type="datetimerange"
    value-format="yyyy-MM-dd HH:mm:ss"
    :clearable="false"
    :picker-options="pickerOptions"
    :range-separator="$t('datepicker.rangeSeparator')"
    :start-placeholder="$t('datepicker.startPlaceholder')"
    :end-placeholder="$t('datepicker.endPlaceholder')"
    align="right"
  />
</template>

<script>
export default {
  data() {
    return {
      clearable: true,
      pickerOptions: {
        shortcuts: [
          {
            text: this.$t('datepicker.today'),
            onClick(picker) {
              const end = new Date()
              const start = new Date(new Date().toLocaleDateString())
              picker.$emit('pick', [start, end])
            }
          },
          {
            text: this.$t('datepicker.yesterday'),
            onClick(picker) {
              const end = new Date(new Date().toLocaleDateString())
              const start = new Date()
              start.setTime(end.getTime() - 3600 * 1000 * 24)
              picker.$emit('pick', [start, end])
            }
          }, {
            text: this.$t('datepicker.thisWeek'),
            onClick(picker) {
              const end = new Date(new Date().toLocaleDateString())
              const start = new Date()
              start.setTime(end.getTime() - 3600 * 1000 * 24 * 7)
              picker.$emit('pick', [start, end])
            }
          }, {
            text: this.$t('datepicker.thisMonth'),
            onClick(picker) {
              const time = new Date()
              const end = new Date()
              const start = new Date(time.getFullYear() + '/' + (parseInt(time.getMonth()) + 1).toString())
              picker.$emit('pick', [start, end])
            }
          }, {
            text: this.$t('datepicker.lastMonth'),
            onClick(picker) {
              const time = new Date()
              const year = time.getFullYear()
              const end = new Date(year + '/' + (parseInt(time.getMonth()) + 1).toString())
              const start = time.getMonth() === '0'
                ? new Date((parseInt(year) - 1).toString() + '/12')
                : new Date(year + '/' + time.getMonth())
              picker.$emit('pick', [start, end])
            }
          }]
      },
      value: [new Date().toLocaleDateString().split('/').join('-') + ' 00:00:00', new Date().toLocaleString().split('/').join('-')]
    }
  }
}
</script>

<style>
</style>
