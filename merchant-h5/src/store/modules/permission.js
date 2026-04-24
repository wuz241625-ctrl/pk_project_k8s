import { asyncRoutes, constantRoutes } from '@/router'

/**
 * 判断用户是否拥有当前路由权限
 * @param routesList
 * @param route
 */
function hasPermission(routesList, route) {
  if (route.meta && route.meta.title && routesList.find(item => item.name === route.meta.title)) {
    return true
  }
  return false
}

/**
 * 通过递归过滤异步路由表
 * @param routes asyncRoutes
 * @param routesList
 */
export function filterAsyncRoutes(routes, routesList) {
  const res = []

  routes.forEach(route => {
    const tmp = { ...route }
    if (hasPermission(routesList, tmp)) {
      if (tmp.children) {
        tmp.children = filterAsyncRoutes(tmp.children, routesList)
      }
      res.push(tmp)
    }
  })

  return res
}

const state = {
  routes: [],
  addRoutes: []
}

const mutations = {
  SET_ROUTES: (state, routes) => {
    state.addRoutes = routes
    state.routes = constantRoutes.concat(routes)
  }
}

const actions = {
  generateRoutes({ commit }, routesList) {
    return new Promise(resolve => {
      var accessedRoutes = filterAsyncRoutes(asyncRoutes, routesList)
      commit('SET_ROUTES', accessedRoutes)
      resolve(accessedRoutes)
    })
  }
}

export default {
  namespaced: true,
  state,
  mutations,
  actions
}
