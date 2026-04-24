// admin/src/utils/pickerOptions.js

/**
 * 日期时间选择器快捷选项配置
 * @param {Function} t - i18n 翻译函数
 * @returns {Object} picker options 配置
 */
export const getDateTimePickerOptions = (t) => {
  return {
    shortcuts: [
      {
        text: t('datepicker.today'),
        onClick(picker) {
          const start = new Date();
          start.setHours(0, 0, 0, 0);
          const end = new Date();
          end.setHours(23, 59, 59, 999);
          picker.$emit('pick', [start, end]);
        }
      },
      {
        text: t('datepicker.yesterday'),
        onClick(picker) {
          const start = new Date();
          start.setTime(start.getTime() - 3600 * 1000 * 24);
          start.setHours(0, 0, 0, 0);
          const end = new Date();
          end.setTime(end.getTime() - 3600 * 1000 * 24);
          end.setHours(23, 59, 59, 999);
          picker.$emit('pick', [start, end]);
        }
      },
      {
        text: t('datepicker.thisWeek'),
        onClick(picker) {
          const end = new Date();
          const start = new Date();
          start.setTime(start.getTime() - 3600 * 1000 * 24 * 7);
          picker.$emit('pick', [start, end]);
        }
      },
      {
        text: t('datepicker.thisMonth'),
        onClick(picker) {
          const start = new Date();
          start.setDate(1);
          start.setHours(0, 0, 0, 0);
          const end = new Date();
          end.setMonth(end.getMonth() + 1);
          end.setDate(0);
          end.setHours(23, 59, 59, 999);
          picker.$emit('pick', [start, end]);
        }
      },
      {
        text: t('datepicker.lastMonth'),
        onClick(picker) {
          const start = new Date();
          start.setMonth(start.getMonth() - 1);
          start.setDate(1);
          start.setHours(0, 0, 0, 0);
          const end = new Date(start);
          end.setMonth(end.getMonth() + 1);
          end.setDate(0);
          end.setHours(23, 59, 59, 999);
          picker.$emit('pick', [start, end]);
        }
      }
    ]
  };
};