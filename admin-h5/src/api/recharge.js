import request from '@/utils/request'

export function createTransfer(data) {
    return request({
        url: '/partner/createtransfer',
        method: 'post',
        data
    })
}

export function getTransfer(data) {
    return request({
        url: '/partner/gettransfer',
        method: 'post',
        data
    })
}

export function handleTransfer(data) {
    return request({
        url: '/partner/handletransfer',
        method: 'post',
        data
    })
}

export function getSystemCard(data) {
    return request({
        url: '/recharge/getsystemcard',
        method: 'post',
        data
    })
}

export function getPayment(data) {
    return request({
        url: '/setting/getpayment',
        method: 'post',
        data
    })
}

export function getRechargePartner(data) {
    return request({
        url: '/recharge/getrechargepartner',
        method: 'post',
        data
    })
}
export function getStaticsReport(data) {
    return request({
        url: '/recharge/getStaticsReport',
        method: 'post',
        data
    })
}
export function addStaticsReport(data) {
    return request({
        url: '/recharge/addStaticsReport',
        method: 'post',
        data
    })
}

export function deleteStaticsReport(data) {
    return request({
        url: '/recharge/deleteStaticsReport',
        method: 'post',
        data
    })
}
export function handleRechargePartner(data) {
    return request({
        url: '/recharge/handlerechargepartner',
        method: 'post',
        data
    })
}

export function getUsdtRechargePartner(data) {
    return request({
        url: '/usdtRecharge/getUsdtRechargePartner',
        method: 'post',
        data
    })
}

export function handleUsdtRechargePartner(data) {
    return request({
        url: '/usdtRecharge/handleUsdtRechargePartner',
        method: 'post',
        data
    })
}

export function getRechargeMerchant(data) {
    return request({
        url: '/recharge/getrechargemerchant',
        method: 'post',
        data
    })
}

export function handleRechargeMerchant(data) {
    return request({
        url: '/recharge/handlerechargemerchant',
        method: 'post',
        data
    })
}

export function getWithdrawPartner(data) {
    return request({
        url: '/recharge/getwithdrawpartner',
        method: 'post',
        data
    })
}

export function handleWithdrawPartner(data) {
    return request({
        url: '/recharge/handlewithdrawpartner',
        method: 'post',
        data
    })
}

export function getWithdrawMerchant(data) {
    return request({
        url: '/recharge/getwithdrawmerchant',
        method: 'post',
        data
    })
}

export function handleWithdrawMerchant(data) {
    return request({
        url: '/recharge/handlewithdrawmerchant',
        method: 'post',
        data
    })
}
