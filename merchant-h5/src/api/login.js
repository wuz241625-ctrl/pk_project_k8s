import request from '@/utils/request'

export function login(data) {
  return request({
    url: '/login/singin',
    method: 'post',
    data
  })
}

export function getInfo() {
  return request({
    url: '/login/getuserinfo',
    method: 'post'
  })
}

export function getRoutes() {
  return request({
    url: '/login/getroutes',
    method: 'post'
  })
}

export function logout() {
  return request({
    url: '/login/singout',
    method: 'post'
  })
}
