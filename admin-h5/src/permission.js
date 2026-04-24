import router from './router'
import store from './store'
import { Message } from 'element-ui'
import NProgress from 'nprogress' // progress bar
import 'nprogress/nprogress.css' // progress bar style
import { getToken } from '@/utils/auth' // get token from cookie
import getPageTitle from '@/utils/get-page-title'
import { getRoutes } from './api/login.js'
import i18n from '@/i18n'
import zhJson from '@/locales/zh.json'; // 导入中文字典文件

NProgress.configure({ showSpinner: false }) // NProgress Configuration

const whiteList = ['/login', '/auth-redirect'] // no redirect whitelist



// 函数：查找键名
function findKeyByValue(obj, value) {
  for (const [key, val] of Object.entries(obj)) {
    if (val === value) {
      return key;
    }
    if (typeof val === 'object') {
      const foundKey = findKeyByValue(val, value);
      if (foundKey) {
        return `${key}.${foundKey}`;
      }
    }
  }
  return null;
}


// 函数：根据中文名称查找英文翻译，限制在 `routes` 开头的字典范围内
export function findI18nKey(name) {
  // 过滤出以 'routes' 开头的键值对
  const routesJson = Object.keys(zhJson)
    .filter(key => key.startsWith('routes'))
    .reduce((obj, key) => {
      obj[key] = zhJson[key];
      return obj;
    }, {});

  const key = findKeyByValue(routesJson, name);
  return key ? i18n.t(key) : 'Not Found';
}


router.beforeEach(async(to, from, next) => {
  // start progress bar
  NProgress.start()

  // set page title
  document.title = getPageTitle(to.meta.title)

  // determine whether the user has logged in
  const hasToken = getToken()
  if (hasToken) {
    if (to.path === '/login') {
      // if is logged in, redirect to the home page
      console.log('自动登录')
      next({ path: '/' })
      NProgress.done() // hack: https://github.com/PanJiaChen/vue-element-admin/pull/2939
    } else {

      // 加载路由
      const hasPermissions = store.getters.permissions
      if (hasPermissions) {
          var res = [];
          store.getters.permission_routes.forEach(route => {
              if(!route.hidden){
                  res.push(route.path);
                  if(route.children){
                      route.children.forEach(route_child => {
                          if(route.path === '/'){
                              res.push('/' + route_child.path);
                          }else {
                              res.push(route.path + '/' + route_child.path);
                          }
                      })
                  }
              }
          })
          if (res && !res.find(item => item === to.path)){
              var path = res[0]
              if (path === '/' && !res.find(item => item === '/Dstj')) {
                  //无/Dstj权限时，取第二个路径跳转
                  path = res[1]
              }
              if(from.path !== path){
                  next(path)
              }

          }else {
              next()
          }
      } else {
        try {
          // 请求用户信息
          const { permissions } = await store.dispatch('user/getInfo')
          // 请求用户路由权限
          const routes = await getRoutes()
          // console.log('翻以前的数据=====', routes.data)
          // 遍历路由，翻译其中的中文字段
          routes.data = routes.data.map(route => {
            const englishTranslation = findI18nKey(route.name);
            if (englishTranslation === 'Not Found') {
              console.log(`ID: ${route.id}, Name: ${route.name} - English translation not found.`);
            }

            return { ...route, name: englishTranslation };
          });
          // console.log('翻以后的数据=====', routes.data)
          // 筛选用户路由
          const accessRoutes = await store.dispatch('permission/generateRoutes', routes.data)
          // hack method to ensure that addRoutes is complete
          // set the replace: true, so the navigation will not leave a history record
          // 动态加载路由
          router.addRoutes(accessRoutes)
          // hack method to ensure that addRoutes is complete
          // set the replace: true, so the navigation will not leave a history record
          next({ ...to, replace: true })
        } catch (error) {
          // 移除登录状态
          await store.dispatch('user/resetToken')
          Message.error(error || 'Has Error')
          next(`/login?redirect=${to.path}`)
          NProgress.done()
        }
      }
    }
  } else {
    /* has no token*/

    if (whiteList.indexOf(to.path) !== -1) {
      // in the free login whitelist, go directly
      next()
    } else {
      // other pages that do not have permission to access are redirected to the login page.
      next(`/login?redirect=${to.path}`)
      NProgress.done()
    }
  }
})

router.afterEach(() => {
  // finish progress bar
  NProgress.done()
})
