<!--
    *名称：弹窗的搜索条件组件
    *功能：methods
      1.点击搜索的方法：@search
      2.搜索条件 props : formItemList
-->

<template>
  <div class="dialog-search">
    <el-form ref="ruleForm" :inline="true" :model="formInline" class="demo-form-inline">
      <el-form-item v-for="(item, index) in formItemList" :key="index" :label="getLabel(item.labelKey)">
        <el-select v-if="item.type === 'select'" v-model="formInline[item.param]" :placeholder="getLabel('search.select_placeholder')" clearable size="mini">
          <el-option v-for="(option, optionIndex) in item.selectOptions" :key="optionIndex" :label="option.label" :value="option.value" />
        </el-select>
        <el-input v-if="item.type === 'input'" v-model="formInline[item.param]" size="mini" :placeholder="getLabel('search.input_placeholder')" />
        <el-date-picker
          v-if="item.type === 'datePicker'"
          v-model="formInline[item.param]"
          value-format="yyyy-MM-dd"
          type="daterange"
          :picker-options="item.pickerOptions"
          :range-separator="getLabel('search.range_separator')"
          :start-placeholder="getLabel('search.start_placeholder_date')"
          :end-placeholder="getLabel('search.end_placeholder_date')"
          size="mini"
        />
        <el-date-picker
          v-if="item.type === 'dateTimePicker'"
          v-model="formInline[item.param]"
          value-format="yyyy-MM-dd HH:mm:ss"
          type="datetimerange"
          :picker-options="item.pickerOptions"
          :range-separator="getLabel('search.range_separator')"
          :start-placeholder="getLabel('search.start_placeholder_datetime')"
          :end-placeholder="getLabel('search.end_placeholder_datetime')"
          size="mini"
        />
      </el-form-item>
      <el-form-item style="width:20rem">
        <el-button v-if="formItemList.length !== 0" type="primary" size="mini" @click="onSubmit">{{ getLabel('search.search_button') }}</el-button>
        <el-button v-if="formItemList.length !== 0" type="primary" plain size="mini" @click="resetForm">{{ getLabel('search.reset_button') }}</el-button>
        <el-button v-if="exportData" type="warning" plain size="mini" icon="el-icon-document" @click="getExportList">{{ getLabel('search.export_button') }}</el-button>
      </el-form-item>
      <slot />
    </el-form>
  </div>
</template>

<script>
export default {
  name: 'BaseSearch',
  props: {
    formItemList: { // 搜索
      type: Array,
      default() { return [] }
    },
    exportData: { // 导出
      type: Object,
      default() { return null }
    }
  },
  data() {
    return {
      formInline: this.initializeFormInline()
    };
  },
  methods: {
    getLabel(key) {
      return this.$t(key); // 使用国际化键获取对应的文本
    },
    initializeFormInline() {
      return this.formItemList.reduce((acc, item) => {
        acc[item.param] = item.defaultSelect || '';
        return acc;
      }, {});
    },
    onSubmit() {
      this.$emit('search', this.formInline);
    },
    async getExportList() {
      await this.$emit('search', this.formInline, true);
    },
    resetForm() {
      this.formInline = this.formItemList.reduce((acc, item) => {
        acc[item.param] = '';
        return acc;
      }, {});
    },
    formatJson(filterVal, jsonData) {
      return jsonData.map(v => filterVal.map(j => v[j]));
    },
    exportExcel() {
      this.downloadLoading = true;
      import('@/vendor/Export2Excel').then(excel => {
        const data = this.formatJson(this.exportData.filterVal, this.exportData.list);
        excel.export_json_to_excel({
          header: this.exportData.tHeader,
          data,
          filename: this.exportData.filename,
          autoWidth: true,
          bookType: 'xlsx'
        });
      });
      this.downloadLoading = false;
    }
  }
}
</script>

<style lang="scss" scoped>
  .dialog-search{
    margin: 0 16px;
    text-align: left;
    .el-input{
        width: 160px;
    }
    .el-select{
      .el-input__inner{
        height: 50px;
        width: 160px;
      }
    }
  }
</style>
