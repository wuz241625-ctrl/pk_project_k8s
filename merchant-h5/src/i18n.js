import Vue from 'vue';
import VueI18n from 'vue-i18n';
import en from './locales/en.json';
import zh from './locales/zh.json';
import Cookies from 'js-cookie';
Vue.use(VueI18n);

const messages = {
  en,
  zh
};

// 从 Cookies 中读取当前语言
const currentLocale = Cookies.get('locale') || 'en'; // 默认为英文


const i18n = new VueI18n({
  locale: currentLocale, // default locale
  fallbackLocale: currentLocale, // fallback locale
  messages
});


export default i18n;
