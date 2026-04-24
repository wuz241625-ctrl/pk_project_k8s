import request from '@/utils/request'

export function getSysRecord(data) {
  return request({
    url: '/record/getsysrecord',
    method: 'post',
    data
  })
}

export function getBalanceRecord(data) {
  return request({
    url: '/record/getbalancerecord',
    method: 'post',
    data
  })
}

export function getBalancedfRecord(data) {
  return request({
    url: '/record/getbalancedfrecord',
    method: 'post',
    data
  })
}

export function getAccountList(data) {
    return request({
        url: '/record/easypaisa/getaccountlist',
        method: 'post',
        data
    })
}

export function downloadBill(data) {
    return request({
        url: '/record/easypaisa/downloadbill',
        method: 'post',
        data
    })
}

export function getAccountListJCB(data) {
    return request({
        url: '/record/jazzcash/getaccountlist',
        method: 'post',
        data
    })
}

export function downloadBillJCB(data) {
    return request({
        url: '/record/jazzcash/querybill',
        method: 'post',
        data
    })
}
