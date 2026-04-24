import Vue from 'vue'
import Router from 'vue-router'
import i18n from '@/i18n'  // 引入国际化配置20240807修改

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
export const constantRoutes = [{
        path: '/redirect',
        component: Layout,
        hidden: true,
        children: [{
            path: '/redirect/:path(.*)',
            component: () => import('@/views/redirect/index')
        }]
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
export const asyncRoutes = [{
        path: '/',
        component: Layout,
        redirect: '/Dstj',
        meta: {
            title: i18n.t('routes.dashboard.title'),
            icon: 'dashboard'
        },
        children: [{
                path: 'Dstj',
                name: 'Dstj',
                hidden: true,
                component: () => import('@/views/count/count'),
                meta: {
                    title: i18n.t('routes.statistics.receipt.title'),
                    icon: 'chart',
                }
            }, {
                path: 'Dftj',
                name: 'Dftj',
                hidden: true,
                component: () => import('@/views/count/count_df'),
                meta: {
                    title: i18n.t('routes.statistics.payment.title'),
                    icon: 'chart',
                }
            }, {
                path: 'sjtj',
                component: () => import('@/views/count/index'),
                redirect: 'noRedirect',
                meta: {
                    title: i18n.t('routes.statistics.data.title'),
                    icon: 'chart',
                },
                // 多级目录下，可以直接redirect到二级目录下，才可以缓存
                children: [{
                    path: 'Dstj',
                    redirect: '/Dstj',
                    meta: {
                            title: i18n.t('routes.statistics.receipt.title'),
                        icon: 'chart'
                    }
                }, {
                    path: 'Dftj',
                    redirect: '/Dftj',
                    meta: {
                            title: i18n.t('routes.statistics.payment.title'),
                        icon: 'chart'
                    }
                }]
            },
            {
                path: 'shmsye',
                component: () => import('@/views/count/balance'),
                name: 'shmsye',
                meta: {
                    title: i18n.t('routes.balance.title'),
                    icon: 'money'
                }
            },
            {
                path: 'cwbb',
                component: () => import('@/views/count/daily'),
                name: 'cwbb',
                meta: {
                    title: i18n.t('routes.financeReport.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'glyczxt',
                component: () => import('@/views/count/adminoperate'),
                name: 'glyczxt',
                meta: {
                    title: i18n.t('routes.operationStats.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'czrz',
                component: () => import('@/views/count/operate'),
                name: 'czrz',
                meta: {
                    title: i18n.t('routes.operationLog.title'),
                    icon: 'eye-open'
                }
            },
            {
                path: 'collectPartner',
                component: () => import('@/views/count/collectPartner'),
                name: 'collectPartner',
                meta: {
                    title: i18n.t('routes.collectPartner.title'),
                    icon: 'chart'
                }
            }
        ]
    },
    {
        path: '/ddgl',
        component: Layout,
        meta: {
            title: i18n.t('routes.orderManagement.title'),
            icon: 'excel'
        },
        redirect: 'noRedirect',
        children: [{
                path: 'Dsdd',
                component: () => import('@/views/order/ds'),
                name: 'Dsdd',
                meta: {
                    title: i18n.t('routes.order.receipt.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Dsddcd',
                component: () => import('@/views/order/dscd'),
                name: 'Dsddcd',
                meta: {
                    title: i18n.t('routes.order.payinCd.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Dfdd',
                component: () => import('@/views/order/df'),
                name: 'Dfdd',
                meta: {
                    title: i18n.t('routes.order.payment.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'AutoDfddMonitor',
                component: () => import('@/views/order/auto_df_monitor'),
                name: 'AutoDfddMonitor',
                meta: {
                    title: i18n.t('routes.order.autoPaymentMonitor.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Mstxdd',
                component: () => import('@/views/order/withdraw_partner'),
                name: 'Mstxdd',
                meta: {
                    title: i18n.t('routes.order.codeMerchantWithdraw.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Msczdd',
                component: () => import('@/views/order/recharge_partner'),
                name: 'Msczdd',
                meta: {
                    title: i18n.t('routes.order.codeMerchantRecharge.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Msczddss',
                component: () => import('@/views/order/recharge_statics'),
                name: 'Msczddss',
                meta: {
                    title: i18n.t('routes.order.codeMerchantStatics.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Msusdtczdd',
                component: () => import('@/views/order/usdt_recharge'),
                name: 'Msusdtczdd',
                meta: {
                    title: i18n.t('routes.order.codeMerchantUsdtRecharge.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Mszzdd',
                component: () => import('@/views/order/transfer'),
                name: 'Mszzdd',
                meta: {
                    title: i18n.t('routes.order.codeMerchantTransfer.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Shtxdd',
                component: () => import('@/views/order/withdraw_merchant'),
                name: 'Shtxdd',
                meta: {
                    title: i18n.t('routes.order.merchantWithdraw.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'bank_withdrawal',
                component: () => import('@/views/order/bank_withdrawal'),
                name: 'bank_withdrawal',
                meta: {
                    title: i18n.t('routes.order.bankWithdrawal.title'),
                    icon: 'documentation'
                }
            }
        ]
    },
    {
        path: '/zjls',
        component: Layout,
        meta: {
            title: i18n.t('routes.fundsFlow.title'),
            icon: 'money'
        },
        redirect: 'noRedirect',
        children: [{
                path: 'Stls',
                component: () => import('@/views/recode/system'),
                name: 'Stls',
                meta: {
                    title: i18n.t('routes.fundsFlow.systemCard.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Yels',
                component: () => import('@/views/recode/balanceds'),
                name: 'Yels',
                meta: {
                    title: i18n.t('routes.fundsFlow.balance.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'easypaisa-bills',
                component: () => import('@/views/recode/easypaisa/itemizedBill.vue'),
                name: 'easypaisa-bills',
                meta: {
                    title: i18n.t('routes.fundsFlow.itemizedBill.title'),
                    icon: 'documentation'
                }
            }
        ]
    },
    {
        path: '/shgl',
        component: Layout,
        meta: {
            title: i18n.t('routes.merchantManagement.title'),
            icon: 'component'
        },
        redirect: 'noRedirect',
        children: [{
                path: 'Shlb',
                component: () => import('@/views/merchant/merchant'),
                name: 'Shlb',
                meta: {
                    title: i18n.t('routes.merchantManagement.list.title'),
                    icon: 'component'
                }
            },
            {
                path: 'Shpm',
                component: () => import('@/views/merchant/ranking'),
                name: 'Shpm',
                meta: {
                    title: i18n.t('routes.merchantManagement.rank.title'),
                    icon: 'list'
                }
            },
            {
                path: 'Shcgl',
                component: () => import('@/views/merchant/successRate'),
                name: 'Shcgl',
                meta: {
                    title: i18n.t('routes.merchantManagement.rank.title1'),
                    icon: 'list',
                    // noCache: true
                }
            }
        ]
    },
    {
        path: '/msgl',
        component: Layout,
        meta: {
            title: i18n.t('routes.codeMerchantManagement.title'),
            icon: 'peoples'
        },
        redirect: 'noRedirect',
        children: [{
                path: 'Mslb',
                component: () => import('@/views/partner/partner'),
                name: 'Mslb',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.list.title'),
                    icon: 'peoples'
                }
            },
            {
                path: 'Mspm',
                component: () => import('@/views/partner/ranking'),
                name: 'Mspm',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.rank.title'),
                    icon: 'list'
                }
            },
            {
                path: 'Yhpm',
                component: () => import('@/views/partner/bank-rank'),
                name: 'Yhpm',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.bankRank.title'),
                    icon: 'list'
                }
            },
            {
                path: 'Skzl',
                component: () => import('@/views/partner/payment'),
                name: 'Skzl',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.paymentInfo.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Skzls',
                component: () => import('@/views/partner/payment-d'),
                name: 'Skzls',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.deletedPaymentInfo.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Yhjl',
                component: () => import('@/views/partner/bank-record'),
                name: 'Yhjl',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.bankStatement.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Yjgl',
                component: () => import('@/views/partner/phonepe'),
                name: 'Yjgl',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.cloudMachineManagement.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Yhgl',
                component: () => import('@/views/partner/bank-type'),
                name: 'Yhgl',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.bankManagement.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'Dxlb',
                component: () => import('@/views/partner/sms'),
                name: 'Dxlb',
                meta: {
                    title: i18n.t('routes.codeMerchantManagement.smsManagement.title'),
                    icon: 'list'
                }
            },
        ]
    },
    {
        path: '/permission',
        component: Layout,
        redirect: '/permission/member',
        alwaysShow: true, // will always show the root menu
        meta: {
            title: i18n.t('routes.permissionManagement.title'),
            icon: 'user'
        },
        children: [{
                path: 'member',
                component: () => import('@/views/permission/member'),
                name: 'PagePermission',
                meta: {
                    title: i18n.t('routes.permissionManagement.member.title'),
                    icon: 'user'
                }
            },
            {
                path: 'role',
                component: () => import('@/views/permission/role'),
                name: 'RolePermission',
                meta: {
                    title: i18n.t('routes.permissionManagement.role.title'),
                    icon: 'user'
                }
            },
            {
                path: 'permission',
                component: () => import('@/views/permission/permission'),
                name: 'permission',
                meta: {
                    title: i18n.t('routes.permissionManagement.permission.title'),
                    icon: 'user'
                }
            }
        ]
    },
    {
        path: '/event',
        component: Layout,
        redirect: '/event/event',
        alwaysShow: true, // will always show the root menu
        meta: {
            title: i18n.t('routes.eventManagement.title'),
            icon: 'user'
        },
        children: [{
                path: 'event',
                component: () => import('@/views/event/event'),
                name: 'Event',
                meta: {
                    title: i18n.t('routes.eventManagement.event.title'),
                    icon: 'user'
                }
            },
            {
                path: 'eventrule',
                component: () => import('@/views/event/eventrule'),
                name: 'EventRule',
                meta: {
                    title: i18n.t('routes.eventManagement.eventrule.title'),
                    icon: 'user'
                }
            }
            ,
            {
                path: 'eventlogs',
                component: () => import('@/views/event/eventLog'),
                name: 'Eventlogs',
                meta: {
                    title: i18n.t('routes.eventManagement.eventLog.title'),
                    icon: 'user'
                }
            },
            {
                path: 'eventpool',
                component: () => import('@/views/event/event_pool'),
                name: 'EventPool',
                meta: {
                    title: i18n.t('routes.eventManagement.eventpool.title'),
                    icon: 'user'
                }
            },
            {
                path: 'eventchance',
                component: () => import('@/views/event/event_chance'),
                name: 'eventchance',
                meta: {
                    title: i18n.t('routes.eventManagement.eventchance.title'),
                    icon: 'user'
                }
            },
            {
                path: 'eventbeginner',
                component: () => import('@/views/event/event_beginner'),
                name: 'EventBeginner',
                meta: {
                    title: i18n.t('routes.eventManagement.eventbeginner.title'),
                    icon: 'user'
                }
            }
        ]
    },
    {
        path: '/xtsz',
        component: Layout,
        meta: {
            title: i18n.t('routes.systemSettings.title'),
            icon: 'bug'
        },
        redirect: 'noRedirect',
        children: [{
                path: 'tdsz',
                component: () => import('@/views/setting/channel'),
                name: 'tdsz',
                meta: {
                    title: i18n.t('routes.systemSettings.channel.title'),
                    icon: 'example'
                }
            },
            {
                path: 'dspz',
                component: () => import('@/views/setting/channelds'),
                name: 'dspz',
                meta: {
                    title: i18n.t('routes.systemSettings.channel.titleds'),
                    icon: 'example'
                }
            },
            {
                path: 'dfpz',
                component: () => import('@/views/setting/channeldf'),
                name: 'dfpz',
                meta: {
                    title: i18n.t('routes.systemSettings.channel.titledf'),
                    icon: 'example'
                }
            },
            {
                path: 'appsz',
                component: () => import('@/views/setting/appsz'),
                name: 'appsz',
                meta: {
                    title: i18n.t('routes.systemSettings.app.title'),
                    icon: 'example'
                }
            },
            {
                path: 'dfdiscount',
                component: () => import('@/views/setting/dfdiscount'),
                name: 'dfdiscount',
                meta: {
                    title: i18n.t('routes.systemSettings.daifuyouhui.title'),
                    icon: 'example'
                }
            },
            {
                path: 'usdtdfdiscount',
                component: () => import('@/views/setting/usdtdfdiscount'),
                name: 'usdtdfdiscount',
                meta: {
                    title: i18n.t('routes.systemSettings.usdtdaifuyouhui.title'),
                    icon: 'example'
                }
            },
            {
                path: 'xtbmd',
                component: () => import('@/views/setting/system-ip'),
                name: 'xtbmd',
                meta: {
                    title: i18n.t('routes.systemSettings.whitelist.title'),
                    icon: 'skill'
                }
            },
            // usdt转入地址
            {
                path: 'usdtinaddress',
                component: () => import('@/views/setting/usdtinaddress'),
                name: 'usdtinaddress',
                meta: {
                    title: i18n.t('routes.systemSettings.usdtinaddress.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'apihmd',
                component: () => import('@/views/setting/system-ip'),
                name: 'apihmd',
                meta: {
                    title: i18n.t('routes.systemSettings.apiBlacklist.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'xtskxx',
                component: () => import('@/views/setting/system-payment'),
                name: 'xtskxx',
                meta: {
                    title: i18n.t('routes.systemSettings.paymentInfo.title'),
                    icon: 'documentation'
                }
            },
            {
                path: 'vip',
                component: () => import('@/views/setting/vip'),
                name: 'vip',
                meta: {
                    title: i18n.t('routes.systemSettings.vipRules.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'qtsz',
                component: () => import('@/views/setting/other'),
                name: 'qtsz',
                meta: {
                    title: i18n.t('routes.systemSettings.otherSettings.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'multisetting',
                component: () => import('@/views/setting/multi-payin'),
                name: 'multisetting',
                meta: {
                    title: i18n.t('routes.systemSettings.mulitpaySetting.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'message',
                component: () => import('@/views/message/message'),
                name: 'message',
                meta: {
                    title: i18n.t('routes.systemSettings.message.title'),
                    icon: 'message'
                }
            },
            {
                path: 'dsdflocksz',
                component: () => import('@/views/setting/dsdflocksz'),
                name: 'dsdflocksz',
                meta: {
                    title: i18n.t('routes.systemSettings.lockSettings.title'),
                    icon: 'lock'
                }
            },
            {
                path: 'operationlog',
                component: () => import('@/views/system/operationLog/index.vue'),
                name: 'operationlog',
                meta: {
                    title: i18n.t('routes.systemSettings.operationlog.title'),
                    icon: 'skill'
                }
            },
            {
                path: 'merchantPaymentLink',
                component: () => import('@/views/setting/merchantpaylink.vue'),
                name: 'merchantPaymentLink',
                meta: {
                    title: i18n.t('routes.systemSettings.merchantPaymentLink.title'),
                    icon: 'link'
                }
            }
        ]
    },

    /** when your routing map is too long, you can split it into small modules **/
    // componentsRouter,
    // chartsRouter,
    // nestedRouter,
    // tableRouter,

    // {
    //   path: '/error',
    //   component: Layout,
    //   redirect: 'noRedirect',
    //   name: 'ErrorPages',
    //   meta: {
    //     title: 'Error Pages',
    //     icon: '404'
    //   },
    //   children: [
    //     {
    //       path: '401',
    //       component: () => import('@/views/error-page/401'),
    //       name: 'Page401',
    //       meta: { title: '401', noCache: true }
    //     },
    //     {
    //       path: '404',
    //       component: () => import('@/views/error-page/404'),
    //       name: 'Page404',
    //       meta: { title: '404', noCache: true }
    //     }
    //   ]
    // },

    // {
    //   path: '/error-log',
    //   component: Layout,
    //   children: [
    //     {
    //       path: 'log',
    //       component: () => import('@/views/error-log/index'),
    //       name: 'ErrorLog',
    //       meta: { title: 'Error Log', icon: 'bug' }
    //     }
    //   ]
    // },
    // 404 page must be placed at the end !!!
    {
        path: '*',
        redirect: '/404',
        hidden: true
    }
]

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
}

export default router
