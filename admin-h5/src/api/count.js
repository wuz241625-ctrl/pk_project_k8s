import request from '@/utils/request'

export function getCount(data) {
  return request({
    url: '/count/getcount',
    method: 'post',
    data
  })
}

export function getCountOneW(data) {
  return request({
    url: '/count/getcountonew',
    method: 'post',
    data
  })
}

export function getBalance(data) {
  return request({
    url: '/count/balance',
    method: 'post',
    data
  })
}

export function getDaily(data) {
  return request({
    url: `/count/daily`,
    method: 'post',
    data
  })
}

export function adminOperate(data) {
  return request({
    url: `/count/adminoperate`,
    method: 'post',
    data
  })
}

export function getOperate(data) {
  return request({
    url: `/count/operate`,
    method: 'post',
    data
  })
}

export function getCollectPartner(data) {
  return request({
    url: `/count/getcollectpartner`,
    method: 'post',
    data
  })
}

