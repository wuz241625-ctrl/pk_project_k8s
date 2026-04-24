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
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getMerchantSuccessRate(data) {
    return request({
        url: '/merchant/getmerchantsuccessrate',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}
