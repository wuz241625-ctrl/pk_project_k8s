<template>
  <div class="login-container">
    <el-form ref="loginForm" :model="loginForm" :rules="loginRules" class="login-form" autocomplete="on" label-position="left">

      <div class="title-container">
        <h3 class="title">{{ $t('title', {  system: $env.VUE_APP_TITLE}) }}</h3>
      </div>

      <el-form-item prop="username">
        <span class="svg-container">
          <svg-icon icon-class="user" />
        </span>
        <el-input
          ref="username"
          v-model="loginForm.username"
          :placeholder="$t('usernamePlaceholder')"
          name="username"
          type="text"
          tabindex="1"
          autocomplete="on"
        />
      </el-form-item>

      <el-tooltip v-model="capsTooltip" :content="$t('capsLockOn')" placement="right" manual>
        <el-form-item prop="password">
          <span class="svg-container">
            <svg-icon icon-class="password" />
          </span>
          <el-input
            :key="passwordType"
            ref="password"
            v-model="loginForm.password"
            :type="passwordType"
            :placeholder="$t('passwordPlaceholder')"
            name="password"
            tabindex="2"
            autocomplete="on"
            @keyup.native="checkCapslock"
            @blur="capsTooltip = false"
            @keyup.enter.native="handleLogin"
          />
          <span class="show-pwd" @click="showPwd">
            <svg-icon :icon-class="passwordType === 'password' ? 'eye' : 'eye-open'" />
          </span>
        </el-form-item>
      </el-tooltip>

      <el-form-item prop="googlecode">
        <span class="svg-container">
          <svg-icon icon-class="international" />
        </span>
        <el-input
          ref="googlecode"
          v-model="loginForm.googlecode"
          :placeholder="$t('googlecodePlaceholder')"
          name="googlecode"
          type="text"
          maxlength="6"
          tabindex="1"
          autocomplete="on"
        />
      </el-form-item>


      <el-form-item prop="switchLanguage" style="width:138px;">
          <!-- Language Switcher -->
          <!-- Language Switcher as a Dropdown -->
          <el-select v-model="currentLanguage" @change="changeLanguage" placeholder="选择语言">
              <el-option label="中文" value="zh"></el-option>
              <el-option label="English" value="en"></el-option>
          </el-select>
      </el-form-item>

      <el-button :loading="loading" type="primary" style="width:100%;margin-bottom:30px;" @click.native.prevent="handleLogin">{{ $t('loginButton') }}</el-button>
    </el-form>
    <el-dialog :title="$t('dialogTitle')" :visible.sync="dialogVisible" width="30%">
      <span>{{ message }}</span>
      <span slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false">{{ $t('dialogConfirm') }}</el-button>
      </span>
    </el-dialog>
<!--    <helloComponent />-->
  </div>
</template>

<script>
import { validUsername, isSafe } from '@/utils/validate'


import Cookies from 'js-cookie';
import locale from 'element-ui/lib/locale'; // Element UI 的 locale 模块
import enLocale from 'element-ui/lib/locale/lang/en';
import zhLocale from 'element-ui/lib/locale/lang/zh-CN';
import { findI18nKey } from '@/permission'
import { asyncRoutes } from '@/router'
import { loadSystemComponent } from '@/utils/load-component';
// 语言包映射
const locales = {
    en: enLocale,
    zh: zhLocale
};

export default {
  name: 'Login',
  components: {
    helloComponent: () => loadSystemComponent('helloComponent', 'helloComponent'),
  },
  data() {
    console.log(process.env)
    const validateUsername = (rule, value, callback) => {
      if (!validUsername(value)) {
        callback(new Error(this.$t('validation.enterUsername')))
      } else {
        callback()
      }
    }
    const validatePassword = (rule, value, callback) => {
      if (value.length < 6) {
        callback(new Error(this.$t('validation.passwordTooShort')))
      } else if (!isSafe(value)) {
        callback(new Error(this.$t('validation.illegalCharacters')))
      } else {
        callback()
      }
    }
    const validateGoogle = (rule, value, callback) => {
      if (value.length !== 6) {
        callback(new Error(this.$t('validation.enterGoogleCode')))
      } else if (isNaN(value) && !isFinite(value)) {
        callback(new Error(this.$t('validation.invalidGoogleCode')))
      } else {
        callback()
      }
    }
    return {
      // Store the current language
      currentLanguage: this.$i18n.locale,
      loginForm: {
        username: '',
        password: '',
        googlecode: ''
      },
      loginRules: {
        username: [{ required: true, trigger: 'blur', validator: validateUsername }],
        password: [{ required: true, trigger: 'blur', validator: validatePassword }],
        googlecode: [{ required: true, trigger: 'blur', validator: validateGoogle }]
      },
      passwordType: 'password',
      capsTooltip: false,
      loading: false,
      showDialog: false,
      redirect: undefined,
      otherQuery: {},
      message: '',
      dialogVisible: false,
      
    }
  },
  watch: {
    $route: {
      handler: function(route) {
        const query = route.query
        if (query) {
          this.redirect = query.redirect
          this.otherQuery = this.getOtherQuery(query)
        }
      },
      immediate: true
    }
  },
  mounted() {
    if (this.loginForm.username === '') {
      this.$refs.username.focus()
    } else if (this.loginForm.password === '') {
      this.$refs.password.focus()
    } else if (this.loginForm.googlecode === '') {
      this.$refs.googlecode.focus()
    }
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
    checkCapslock(e) {
      const { key } = e
      this.capsTooltip = key && key.length === 1 && (key >= 'A' && key <= 'Z')
    },
    showPwd() {
      if (this.passwordType === 'password') {
        this.passwordType = ''
      } else {
        this.passwordType = 'password'
      }
      this.$nextTick(() => {
        this.$refs.password.focus()
      })
    },
    /* 登录*/
    handleLogin() {
      this.$refs.loginForm.validate(valid => {
        if (valid) {
          this.loading = true
          this.$store.dispatch('user/logIn', this.loginForm)
            .then((res) => {
                var path = this.redirect || '/';
                if('data' in res){
                    //翻译其中的中文字段
                    const englishTranslation = findI18nKey(res.data.name);
                    asyncRoutes.some(route => {
                        return route.children.some(child => {
                            if (child.meta && child.meta.title && englishTranslation === child.meta.title) {
                                if(route.path === '/'){
                                    path = '/' + child.path
                                }else {
                                    path = route.path + '/' +child.path
                                }
                                return true
                            }
                        })
                    })
                }
                this.$router.push({ path: path, query: this.otherQuery })
                this.loading = false
            })
            .catch(() => {
              this.loading = false
            })
        } else {
          console.log('error submit!!')
          return false
        }
      })
    },
    getOtherQuery(query) {
      return Object.keys(query).reduce((acc, cur) => {
        if (cur !== 'redirect') {
          acc[cur] = query[cur]
        }
        return acc
      }, {})
    }
  },
}
</script>

<style lang="scss">
/* 修复input 背景不协调 和光标变色 */
/* Detail see https://github.com/PanJiaChen/vue-element-admin/pull/927 */

$bg:#283443;
$light_gray:#fff;
$cursor: #fff;

@supports (-webkit-mask: none) and (not (cater-color: $cursor)) {
  .login-container .el-input input {
    color: $cursor;
  }
}

/* reset element-ui css */
.login-container {
  .el-input {
    display: inline-block;
    height: 47px;
    width: 85%;

    input {
      background: transparent;
      border: 0px;
      -webkit-appearance: none;
      border-radius: 0px;
      padding: 12px 5px 12px 15px;
      color: $light_gray;
      height: 47px;
      caret-color: $cursor;

      &:-webkit-autofill {
        box-shadow: 0 0 0px 1000px $bg inset !important;
        -webkit-text-fill-color: $cursor !important;
      }
    }
  }

  .el-form-item {
    border: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(0, 0, 0, 0.1);
    border-radius: 5px;
    color: #454545;
  }
}
</style>

<style lang="scss" scoped>
$bg:#2d3a4b;
$dark_gray:#889aa4;
$light_gray:#eee;

.login-container {
  min-height: 100%;
  width: 100%;
  background-color: $bg;
  overflow: hidden;

  .login-form {
    position: relative;
    width: 520px;
    max-width: 100%;
    padding: 160px 35px 0;
    margin: 0 auto;
    overflow: hidden;
  }

  .tips {
    font-size: 14px;
    color: #fff;
    margin-bottom: 10px;

    span {
      &:first-of-type {
        margin-right: 16px;
      }
    }
  }

  .svg-container {
    padding: 6px 5px 6px 15px;
    color: $dark_gray;
    vertical-align: middle;
    width: 30px;
    display: inline-block;
  }

  .title-container {
    position: relative;

    .title {
      font-size: 26px;
      color: $light_gray;
      margin: 0px auto 40px auto;
      text-align: center;
      font-weight: bold;
    }
  }

  .show-pwd {
    position: absolute;
    right: 10px;
    top: 7px;
    font-size: 16px;
    color: $dark_gray;
    cursor: pointer;
    user-select: none;
  }

  .thirdparty-button {
    position: absolute;
    right: 0;
    bottom: 6px;
  }

  @media only screen and (max-width: 470px) {
    .thirdparty-button {
      display: none;
    }
  }
}
</style>
