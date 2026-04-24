import Vue from 'vue'
import Router from 'vue-router'
import i18n from '@/i18n'  // 引入国际化配置

Vue.use(Router)

/* Layout */
import Layout from '@/layout'

/* Router Modules */
// import componentsRouter from './modules/components'
// import chartsRouter from './modules/charts'
// import tableRouter from './modules/table'
// import nestedRouter from './modules/nested'

/**
 * Note: sub-menu only appear when route children.length >= 1
 * Detail see: https://panjiachen.github.io/vue-element-admin-site/guide/essentials/router-and-nav.html
 *
 * hidden: true                   if set true, item will not show in the sidebar(default is false)
 * alwaysShow: true               if set true, will always show the root menu
 *                                if not set alwaysShow, when item has more than one children route,
 *                                it will becomes nested mode, otherwise not show the root menu
 * redirect: noRedirect           if set noRedirect will no redirect in the breadcrumb
 * name:'router-name'             the name is used by <keep-alive> (must set!!!)
 * meta : {
    roles: ['admin','editor']    control the page roles (you can set multiple roles)
    title: 'title'               the name show in sidebar and breadcrumb (recommend set)
    icon: 'svg-name'/'el-icon-x' the icon show in the sidebar
    noCache: true                if set true, the page will no be cached(default is false)
    affix: true                  if set true, the tag will affix in the tags-view
    breadcrumb: false            if set false, the item will hidden in breadcrumb(default is true)
    activeMenu: '/example/list'  if set path, the sidebar will highlight the path you set
  }
 */

/**
 * constantRoutes
 * a base page that does not have permission requirements
 * all roles can be accessed
 */
export const constantRoutes = [
    {
        path: '/redirect',
        component: Layout,
        hidden: true,
        children: [
            {
                path: '/redirect/:path(.*)',
                component: () => import('@/views/redirect/index')
            }
        ]
    },
    {
        path: '/login',
        component: () => import('@/views/login/index'),
        hidden: true
    },
    {
        path: '/auth-redirect',
        component: () => import('@/views/login/auth-redirect'),
        hidden: true
    },
    {
        path: '/',
        component: Layout,
        redirect: '/dashboard',
        meta: {
            title: i18n.t('menu.dashboard'),
            icon: 'dashboard'
        },
        children: [
            {
                path: 'dashboard',
                component: () => import('@/views/count/count'),
                name: 'dashboard',
                meta: {
                    title: i18n.t('menu.collectionStats'),
                    icon: 'chart'
                }
            },
            {
                path: 'payment-stats',
                component: () => import('@/views/count/count'),
                name: 'payment-stats',
                meta: {
                    title: i18n.t('menu.paymentStats'),
                    icon: 'chart'
                }
            },
            {
                path: 'balance-flow',
                component: () => import('@/views/count/balance'),
                name: 'balance-flow',
                meta: {
                    title: i18n.t('menu.balanceFlow'),
                    icon: 'documentation'
                }
            },
        ]
    },
    {
        path: '/order-management',
        component: Layout,
        meta: {
            title: i18n.t('menu.orderManagement'),
            icon: 'excel'
        },
        redirect: 'noRedirect',
        children: [
            {
                path: 'collection-orders',
                component: () => import('@/views/order/ds'),
                name: 'collection-orders',
                meta: {
                    title: i18n.t('menu.collectionOrders'),
                    icon: 'documentation'
                }
            },
            {
                path: 'payment-orders',
                component: () => import('@/views/order/df'),
                name: 'payment-orders',
                meta: {
                    title: i18n.t('menu.paymentOrders'),
                    icon: 'documentation'
                }
            },
            {
                path: 'withdrawal-orders',
                component: () => import('@/views/order/withdraw'),
                name: 'withdrawal-orders',
                meta: {
                    title: i18n.t('menu.withdrawalOrders'),
                    icon: 'documentation'
                }
            },
        ]
    },
    {
        path: '/merchant-management',
        component: Layout,
        meta: {
            title: i18n.t('menu.merchantManagement'),
            icon: 'component'
        },
        redirect: 'noRedirect',
        children: [
            {
                path: 'merchant-list',
                component: () => import('@/views/merchant/merchant'),
                name: 'merchant-list',
                meta: {
                    title: i18n.t('menu.merchantList'),
                    icon: 'component'
                }
            },
            {
                path: 'merchant-ranking',
                component: () => import('@/views/merchant/ranking'),
                name: 'merchant-ranking',
                meta: {
                    title: i18n.t('menu.merchantRanking'),
                    icon: 'list'
                }
            }
        ]
    },
    {
        path: '/system-settings',
        component: Layout,
        meta: {
            title: i18n.t('menu.systemSettings'),
            icon: 'bug'
        },
        redirect: 'noRedirect',
        children: [
            {
                path: 'channel-info',
                component: () => import('@/views/setting/channel'),
                name: 'channel-info',
                meta: {
                    title: i18n.t('menu.channelInfo'),
                    icon: 'example'
                }
            },
            {
                path: 'personal-info',
                component: () => import('@/views/setting/setting'),
                name: 'personal-info',
                meta: {
                    title: i18n.t('menu.personalInfo'),
                    icon: 'bug'
                }
            }
        ]
    },
    {
        path: '/404',
        component: () => import('@/views/error-page/404'),
        hidden: true
    },
    {
        path: '/401',
        component: () => import('@/views/error-page/401'),
        hidden: true
    }
]

/**
 * asyncRoutes
 * the routes that need to be dynamically loaded based on user roles
 */
export const asyncRoutes = []

const createRouter = () => new Router({
    // mode: 'history', // require service support
    scrollBehavior: () => ({
        y: 0
    }),
    routes: constantRoutes
})

const router = createRouter()

// Detail see: https://github.com/vuejs/vue-router/issues/1234#issuecomment-357941465
export function resetRouter() {
    const newRouter = createRouter()
    router.matcher = newRouter.matcher // reset router
    //alert('Router has been reset')
}

export default router
