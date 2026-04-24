import Vue from 'vue'

import Cookies from 'js-cookie'

import 'normalize.css/normalize.css' // a modern alternative to CSS resets

import Element from 'element-ui'
import './styles/element-variables.scss'
// import enLang from 'element-ui/lib/locale/lang/en'// 如果使用中文语言包请默认支持，无需额外引入，请删除该依赖

import '@/styles/index.scss' // global css

import App from './App'
import store from './store'
import router from './router'

import './icons' // icon
import './permission' // permission control
import './utils/error-log' // error log

import * as filters from './filters' // global filters

import baseComponents from './views/components/index.js'

import i18n from './i18n'; // Import i18n instance
import VueI18n from 'vue-i18n';

// // // Set the locale from cookies if available
// const localeTmp = Cookies.get('locale') || 'en'; // Default to 'en' if not set
// i18n.locale = localeTmp;

import ElementUI from 'element-ui';
import 'element-ui/lib/theme-chalk/index.css';

import locale from 'element-ui/lib/locale';
import enLocale from 'element-ui/lib/locale/lang/en';
import zhLocale from 'element-ui/lib/locale/lang/zh-CN';
// 语言包映射
const locales = {
  en: enLocale,
  zh: zhLocale
};

Vue.use(ElementUI, { locale: enLocale });
Vue.prototype.$env = process.env

/**
 * If you don't want to use mock-server
 * you want to use MockJs for mock api
 * you can execute: mockXHR()
 *
 * Currently MockJs will be used in the production environment,
 * please remove it before going online ! ! !
 */
// if (process.env.NODE_ENV === 'production') {
//   const { mockXHR } = require('../mock')
//   mockXHR()
// }

Vue.use(Element, {
  size: Cookies.get('size') || 'medium' // set element-ui default size
  // locale: enLang // 如果使用中文，无需设置，请删除
})

// register global utility filters
Object.keys(filters).forEach(key => {
  Vue.filter(key, filters[key])
})

// register baseComponents
Vue.use(baseComponents)

Vue.config.productionTip = false


// Set the locale from cookies if available
const localeLan = Cookies.get('locale') || 'en'; // Default to 'en' if not set
// i18n.locale = locale;

// import i18n from './i18n'; // Import i18n instance
// i18n.locale = locale1;
// i18n.messages = messages;

const messages = {
  "en": {
    ...enLocale,
    "el": {
      "table": {
        "emptyText": "No Data"
      },
      "pagination": {
        "total": "Total {total} items",
        "pagesize": " items/page",
        "goto": "Go to",
        "pageClassifier": ""
      },
      "datepicker": {
        "startTime": "Start Time",
        "endTime": "End Time",
        "weeks": {
          "sun": "Sun",
          "mon": "Mon",
          "tue": "Tue",
          "wed": "Wed",
          "thu": "Thu",
          "fri": "Fri",
          "sat": "Sat"
        },
        "year": "Year",
        "month1": "January",
        "month2": "February",
        "month3": "March",
        "month4": "April",
        "month5": "May",
        "month6": "June",
        "month7": "July",
        "month8": "August",
        "month9": "September",
        "month10": "October",
        "month11": "November",
        "month12": "December",
        "month": "Month",
        "startDate": "Start Date",
        "endDate": "End Date",
        "selectDate": "Select Date",
        "selectTime": "Select Time",
        "now": "Now",
        "today": "Today",
        "clear": "Clear",
        "confirm": "Confirm",
        "cancel": "Cancel",
        // Add other fields as needed
      }
    },
    "message": {
      "hello": "Hello World"
    }
  },
  "zh": {
    ...zhLocale,
    "el": {
      "table": {
        "emptyText": "暂无数据"
      },
      "pagination": {
        "total": "共 {total} 条",
        "pagesize": " 条/页",
        "goto": "前往",
        "pageClassifier": "页"
      },
      "datepicker": {
        "startTime": "开始时间",
        "endTime": "结束时间",
        "weeks": {
          "sun": "日",
          "mon": "一",
          "tue": "二",
          "wed": "三",
          "thu": "四",
          "fri": "五",
          "sat": "六"
        },
        "year": "年",
        "month1": "一月",
        "month2": "二月",
        "month3": "三月",
        "month4": "四月",
        "month5": "五月",
        "month6": "六月",
        "month7": "七月",
        "month8": "八月",
        "month9": "九月",
        "month10": "十月",
        "month11": "十一月",
        "month12": "十二月",
        "month": "月",
        "startDate": "开始日期",
        "endDate": "结束日期",
        "selectDate": "选择日期",
        "selectTime": "选择时间",
        "now": "现在",
        "today": "今天",
        "clear": "清除",
        "confirm": "确定",
        "cancel": "取消",
        // Add other fields as needed
      }
    },
    "message": {
      "hello": "你好，世界"
    }
  }
};
const i18n1 = new VueI18n({
  locale: localeLan, // 默认语言
  messages
});

locale.i18n((key, value) => i18n1.t(key, value));

new Vue({
  el: '#app',
  router,
  store,
  i18n,
  i18n1, // Include i18n
  render: h => h(App),
  data: {
    currentLang: 'zh' // 默认语言
  },
  watch: {
    currentLang(newLang) {
      this.setElementUILocale(newLang);
    }
  },
  methods: {
    setElementUILocale(lang) {
      if (lang === 'zh') {
        locale.use(zhLocale);
      } else {
        locale.use(enLocale);
      }
    }
  },
  created() {
    this.setElementUILocale(this.currentLang);
  }
})
