<template>
  <div class="navbar">
    <hamburger id="hamburger-container" :is-active="sidebar.opened" class="hamburger-container" @toggleClick="toggleSideBar" />

    <breadcrumb id="breadcrumb-container" class="breadcrumb-container" />

    <div class="right-menu">
      <template v-if="device!=='mobile'">
        <search id="header-search" class="right-menu-item" />

        <screenfull id="screenfull" class="right-menu-item hover-effect" />

        <el-tooltip content="布局大小" effect="dark" placement="bottom">
          <size-select id="size-select" class="right-menu-item hover-effect" />
        </el-tooltip>


        <!-- Language Switcher -->
        <!-- Language Switcher as a Dropdown -->
        <el-tooltip content="切换语言" effect="dark" placement="bottom">
          <el-select v-model="currentLanguage" @change="changeLanguage" class="language-switcher right-menu-item hover-effect" placeholder="选择语言">
            <el-option label="中文" value="zh"></el-option>
            <el-option label="English" value="en"></el-option>
          </el-select>
        </el-tooltip>


      </template>

      <el-dropdown class="avatar-container right-menu-item hover-effect" trigger="click">
        <div class="avatar-wrapper">
          <span type="primary">{{ name + '('+ id + ')' }}</span>
          <i class="el-icon-caret-bottom" />
        </div>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item divided @click.native="logout">
            <span style="display:block;">{{ $t('login_out') }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>
  </div>
</template>

<script>
import { mapGetters } from 'vuex'
import Breadcrumb from '@/components/Breadcrumb'
import Hamburger from '@/components/Hamburger'
import Screenfull from '@/components/Screenfull'
import SizeSelect from '@/components/SizeSelect'
import Search from '@/components/HeaderSearch'
import Cookies from 'js-cookie';
import locale from 'element-ui/lib/locale'; // Element UI 的 locale 模块
import enLocale from 'element-ui/lib/locale/lang/en';
import zhLocale from 'element-ui/lib/locale/lang/zh-CN';

// 语言包映射
const locales = {
    en: enLocale,
    zh: zhLocale
};

export default {
  data() {
    return {
      // Store the current language
      currentLanguage: this.$i18n.locale,
    };
  },
  components: {
    Breadcrumb,
    Hamburger,
    Screenfull,
    SizeSelect,
    Search
  },
  computed: {
    ...mapGetters([
      'sidebar',
      'name',
      'id',
      'device'
    ])
  },
  methods: {
    async changeLanguage(lang) {
      // 检查语言包是否已经加载
      if (!this.$i18n.getLocaleMessage(lang)) {
        const messages = await this.loadLanguageAsync(lang);
        this.$i18n.setLocaleMessage(lang, messages);
      }
      
      // 更新 Vue I18n 实例中的语言
      this.$i18n.locale = lang;
      this.currentLanguage = lang;
      Cookies.set('locale', lang, { path: '/' });
      this.$root.currentLang = lang;
      
      // 更新 Element UI 的语言设置
      const elementLocale = locales[lang] || enLocale; // 获取对应的 Element UI 语言包
      locale.use(elementLocale);
      
      // 强制更新 Vue 组件
      this.$forceUpdate();
      window.location.reload();
    },
    
    loadLanguageAsync(lang) {
      return fetch(`/locales/${lang}.json`)
        .then(response => response.json());
    },
    toggleSideBar() {
      this.$store.dispatch('app/toggleSideBar')
    },
    async logout() {
      await this.$store.dispatch('user/logOut')
      this.$router.push(`/login?redirect=${this.$route.fullPath}`)
    }
  }
}
</script>

<style lang="scss" scoped>
.navbar {
  height: 50px;
  overflow: hidden;
  position: relative;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0,21,41,.08);

  .hamburger-container {
    line-height: 46px;
    height: 100%;
    float: left;
    cursor: pointer;
    transition: background .3s;
    -webkit-tap-highlight-color:transparent;

    &:hover {
      background: rgba(0, 0, 0, .025)
    }
  }

  .breadcrumb-container {
    float: left;
  }
  .right-menu {
    float: right;
    height: 100%;
    line-height: 50px;

    &:focus {
      outline: none;
    }

    .right-menu-item {
      display: inline-block;
      padding: 0 8px;
      height: 100%;
      font-size: 18px;
      color: #5a5e66;
      vertical-align: text-bottom;

      &.hover-effect {
        cursor: pointer;
        transition: background .3s;

        &:hover {
          background: rgba(0, 0, 0, .025)
        }
      }
    }

    .avatar-container {
      margin-right: 30px;

      .avatar-wrapper {
        position: relative;
      }
    }
  }
}
.language-switcher {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.language-switcher span {
  margin-right: 10px;
}

.language-switcher .active {
  font-weight: bold;
  color: #409EFF; /* Active color */
}
</style>
