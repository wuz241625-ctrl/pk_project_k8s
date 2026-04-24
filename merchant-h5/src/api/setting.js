import request from '@/utils/request'


export function getChannel(data) {
  return request({
    url: '/setting/getchannel',
    method: 'post',
    data
  })
}

export function getIP(data) {
  return request({
    url: '/setting/getip',
    method: 'post',
    data
  })
}

export function updateIP(data) {
  return request({
    url: '/setting/updateip',
    method: 'post',
    data
  })
}

export function getInfo(data) {
  return request({
    url: '/setting/getinfo',
    method: 'post',
    data
  })
}

export function checkGg(data) {
  return request({
    url: '/setting/checkgg',
    method: 'post',
    data
  })
}

export function resetGg(data) {
  return request({
    url: '/setting/resetgg',
    method: 'post',
    data
  })
}

export function resetPw(data) {
  return request({
    url: '/setting/resetpw',
    method: 'post',
    data
  })
}
