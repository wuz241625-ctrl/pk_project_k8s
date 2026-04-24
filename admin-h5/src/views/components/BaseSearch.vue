<!--
    *名称：弹窗的搜索条件组件
    *功能：methods
      1.点击搜索的方法：@search
      2.搜索条件 props : formItemList
-->

<template>
  <div class="dialog-search">
    <el-form ref="ruleForm" :inline="true" :model="formInline" class="demo-form-inline">
      <el-form-item v-for="(item, index) in formItemList" :key="index" :label="$t(item.label)">
        <el-select
          v-if="item.type === 'select'"
          :multiple="item.multiple"
          v-model="formInline[item.param]"
          :placeholder="$t('search.selectPlaceholder')"
          clearable
          :filterable="item.filterable"
          size="mini"
        >
          <el-option
            v-for="(option, optionIndex) in item.selectOptions"
            :key="optionIndex"
            :label="$t(option.label)"
            :value="option.value"
          />
        </el-select>
        <el-input
          v-if="item.type === 'input'"
          v-model="formInline[item.param]"
          size="mini"
          :placeholder="$t('search.inputPlaceholder')"
        />
        <el-date-picker
          v-if="item.type === 'datePicker'"
          v-model="formInline[item.param]"
          value-format="yyyy-MM-dd"
          type="daterange"
          :picker-options="item.pickerOptions"
          :range-separator="$t('search.dateRangeSeparator')"
          :start-placeholder="$t('search.startDate')"
          :end-placeholder="$t('search.endDate')"
          size="mini"
        />
        <el-date-picker
          v-if="item.type === 'dateTimePicker'"
          v-model="formInline[item.param]"
          value-format="yyyy-MM-dd HH:mm:ss"
          type="datetimerange"
          :picker-options="item.pickerOptions"
          :range-separator="$t('search.dateTimeRangeSeparator')"
          :start-placeholder="$t('search.startTime')"
          :end-placeholder="$t('search.endTime')"
          size="mini"
        />
      </el-form-item>
      <el-form-item>
        <el-button
          v-if="formItemList.length !== 0"
          :disabled="isQueryDisabled"
          type="primary"
          size="mini"
          @click="onSubmit"
        >{{ $t('search.query') }}</el-button>
        <el-button
          v-if="formItemList.length !== 0"
          type="primary"
          plain
          size="mini"
          @click="resetForm"
        >{{ $t('search.reset') }}</el-button>
        <el-button
          v-if="exportData"
          :disabled="isDisabled"
          type="warning"
          plain
          size="mini"
          icon="el-icon-document"
          @click="getExportList(0)"
        >{{ $t('search.export') }}</el-button>
        <el-button
          v-if="exportBankData"
          :disabled="isDisabled"
          type="warning"
          plain
          size="mini"
          icon="el-icon-document"
          @click="getExportList(1)"
        >{{ $t('search.exportBank') }}</el-button>
        <el-button
          v-if="showRefresh"
          plain
          size="mini"
          icon="el-icon-refresh-left"
          @click="$emit('search')"
        >{{ $t('search.refresh') }}</el-button>
      </el-form-item>
      <slot />
    </el-form>
  </div>
</template>


<script>
export default {
  name: 'BaseSearch',
  props: {
    showRefresh:{
      type: Boolean,
      default: false
    },
        formItemList: { // 搜索
      type: Array,
      default() {
        return []
      }
    },
        exportData: { // 导出
      type: Object,
      default() {
        return null
      }
    },
        exportBankData: { // 导出
      type: Object,
      default() {
        return null
      }
    },
        isdisable: { // 导出
      type: Number,
      default() {
        return 0
      }
    },
    showExportTips: {
      type: Boolean,
      default: true
    }
  },
  data() {
    const formInline = {}
    for (const obj of this.formItemList) {
      formInline[obj.param] = obj.defaultSelect || ''
    }
    return {
      formInline,
      is_exportBank: false,
      isDisabled: false,
      isQueryDisabled: false
    }
  },
  methods: {
    searchData() {
      this.$emit('search', this.formInline)
    },
    onSubmit() {
      this.$emit('search', this.formInline)
            // 限制点击
      this.isQueryDisabled = true
            if (this.isdisable > 0) {
      setTimeout(() => {
        this.isQueryDisabled = false
                }, this.isdisable * 1000)
            } else {
                setTimeout(() => {
                    this.isQueryDisabled = false
                }, 2000)
            }
    },
    async getExportList(_type) {
      this.is_exportBank = _type === 1
      await this.$emit('search', this.formInline, true)
            // 限制点击
      this.isDisabled = true
      if (this.showExportTips) {
        this.$message({
          type: 'success',
          message: this.$t('search.exportMessage')
        })
      }
      setTimeout(() => {
        this.isDisabled = false
      }, 30000)
    },
        /* 重置 */
    resetForm() {
      const formInline = {}
      for (const obj of this.formItemList) {
        formInline[obj.param] = ''
      }
      this.formInline = formInline
    },
        /* 转化为Json */
    formatJson(filterVal, jsonData) {
      return jsonData.map(v => filterVal.map(j => {
        return v[j]
      }))
    },
        /* 导出excel */
    exportExcel() {
      this.downloadLoading = true
      import('@/vendor/Export2Excel').then(excel => {
        var exportData = this.is_exportBank ? this.exportBankData : this.exportData
        const data = this.formatJson(exportData.filterVal, exportData.list);
        excel.export_json_to_excel({
          header: exportData.tHeader,
          data: data,
          colTypes: excel.getColumnTypes(this.$getFormattedRoute(), this.$exportColSettings, exportData.filterVal),
          filename: exportData.filename,
          autoWidth: true,
          bookType: 'xlsx'
        })
      })
      this.downloadLoading = false
    }
  }
}
</script>

<style lang="scss" scoped>
    .dialog-search {
        margin: 0 16px;
        text-align: left;

        .el-input {
            width: 160px;
        }

        .el-select {
            .el-input__inner {
                height: 50px;
                width: 160px;
            }
        }
    }
</style>
