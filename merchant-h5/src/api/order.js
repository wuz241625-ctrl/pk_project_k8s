import request from '@/utils/request'

export function getOrderds(data) {
  return request({
    url: '/order/getorderds',
    method: 'post',
    data
  })
}

export function getOrderdf(data) {
  return request({
    url: '/order/getorderdf',
    method: 'post',
    data
  })
}

export function addDf(data) {
  return request({
    url: '/order/adddf',
    method: 'post',
    data
  })
}

export function addDfpl(data) {
  return request({
    url: '/order/adddfpl',
    method: 'post',
    data
  })
}

export function getRecharge(data) {
  return request({
    url: '/order/getrecharge',
    method: 'post',
    data
  })
}

export function addRecharge(data) {
  return request({
    url: '/order/addrecharge',
    method: 'post',
    data
  })
}

export function getWithdraw(data) {
  return request({
    url: '/order/getwithdraw',
    method: 'post',
    data
  })
}

export function addWithdraw(data) {
  return request({
    url: '/order/addwithdraw',
    method: 'post',
    data
  })
}

export function getTransfer(data) {
  return request({
    url: '/order/gettransfer',
    method: 'post',
    data
  })
}

export function addTransfer(data) {
  return request({
    url: '/order/addtransfer',
    method: 'post',
    data
  })
}
