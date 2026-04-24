import request from '@/utils/request'

export function getMerchant(data) {
  return request({
    url: '/merchant/getmerchant',
    method: 'post',
    data
  })
}

export function addMerchant(data) {
  return request({
    url: '/merchant/addmerchant',
    method: 'post',
    data
  })
}

export function updateMerchant(data) {
  return request({
    url: `/merchant/updatemerchant`,
    method: 'post',
    data
  })
}

export function getMerchantChannel(data) {
  return request({
    url: `/merchant/getmerchantchannel`,
    method: 'post',
    data
  })
}

export function updateMerchantChannel(data) {
  return request({
    url: `/merchant/updatemerchantchannel`,
    method: 'post',
    data
  })
}

export function resetGgkey(data) {
  return request({
    url: `/merchant/resetggkey`,
    method: 'post',
    data
  })
}

export function getMerchantRank(data) {
  return request({
    url: '/merchant/getmerchantrank',
    method: 'post',
    data
  })
}
