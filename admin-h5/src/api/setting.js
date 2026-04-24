import request from '@/utils/request'

export function switchPaymentServiceState() {
    return request({
        url: '/setting/switchPaymentServiceState',
        method: 'post'
    })
}

export function getPaymentServiceState() {
    return request({
        url: '/setting/getPaymentServiceState',
        method: 'post'
    })
}

export function switchJazzCashPayoutServiceState() {
    return request({
        url: '/setting/switchJazzCashPayoutServiceState',
        method: 'post'
    })
}

export function getJazzCashPayoutServiceState() {
    return request({
        url: '/setting/getJazzCashPayoutServiceState',
        method: 'post'
    })
}

export function getOtherPay() {
    return request({
        url: '/setting/getotherpay',
        method: 'post'
    })
}

export function changeOtherPay(data) {
    return request({
        url: '/setting/changeotherpay',
        method: 'post',
        data
    })
}

export function getChannel(data) {
    return request({
        url: '/setting/getchannel',
        method: 'post',
        data
    })
}

export function updateChannel(data) {
    return request({
        url: `/setting/updatechannel`,
        method: 'post',
        data
    })
}

export function testOrder(data) {
    return request({
        url: `/setting/testorder`,
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

export function addPayment(data) {
    return request({
        url: '/setting/addpayment',
        method: 'post',
        data
    })
}

export function updatePayment(data) {
    return request({
        url: `/setting/updatepayment`,
        method: 'post',
        data
    })
}

export function deletePayment(data) {
    return request({
        url: `/setting/deletepayment`,
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

export function getOther() {
    return request({
        url: '/setting/getother',
        method: 'post'
    })
}

export function getAppsz() {
    return request({
        url: '/setting/getappsz',
        method: 'post'
    })
}

export function updateAppsz(data) {
    return request({
        url: '/setting/updateappsz',
        method: 'post',
        data
    })
}

export function getDfdiscount() {
    return request({
        url: '/setting/getdfdiscount',
        method: 'post'
    })
}

export function updateDfdiscount(data) {
    return request({
        url: '/setting/updatedfdiscount',
        method: 'post',
        data
    })
}

export function getUsdtDfDiscount() {
    return request({
        url: '/setting/getUsdtDfDiscount',
        method: 'post'
    })
}

export function updateUsdtDfdiscount(data) {
    return request({
        url: '/setting/updateUsdtDfdiscount',
        method: 'post',
        data
    })
}

export function getWeight() {
    return request({
        url: '/setting/getweight',
        method: 'post'
    })
}

export function updateWeight(data) {
    return request({
        url: '/setting/updateweight',
        method: 'post',
        data
    })
}

export function updateOther(data) {
    return request({
        url: '/setting/updateother',
        method: 'post',
        data
    })
}

export function getVip() {
    return request({
        url: '/setting/getvip',
        method: 'post',
    })
}

export function updateVip(data) {
    return request({
        url: '/setting/updatevip',
        method: 'post',
        data
    })
}


export function getUsdtTransferAddress() {
    return request({
        url: '/setting/getUsdtTransferAddress',
        method: 'post',
    })
}

export function updateUsdtTransferAddress(data) {
    return request({
        url: '/setting/updateUsdtTransferAddress',
        method: 'post',
        data
    })
}

export function getDsdfLockSettings() {
    return request({
        url: '/setting/getDsdfLockSettings',
        method: 'post',
    })
}

export function updateDsdfLockSettings(data) {
    return request({
        url: '/setting/updateDsdfLockSettings',
        method: 'post',
        data
    })
}

export function getMerchantPayLink(data) {
    return request({
        url: '/setting/MerchantPayLinks',
        method: 'get',
        data
    })
}

export function addMerchantPayLink(data) {
    return request({
        url: '/setting/MerchantPayLinks',
        method: 'post',
        data
    })
}

export function editMerchantPayLink(data) {
    return request({
        url: '/setting/MerchantPayLinks',
        method: 'put',
        data
    })
}

export function delMerchantPayLink(data) {
    return request({
        url: '/setting/MerchantPayLinks',
        method: 'delete',
        data
    })
}

export function getDSSettings(data) {
    return request({
        url: '/setting/getDSSettings',
        method: 'post',
        data
    })
}

export function addDSSettings(data) {
    return request({
        url: '/setting/addDSSettings',
        method: 'post',
        data
    })
}

export function delDSSettings(data) {
    return request({
        url: '/setting/delDSSettings',
        method: 'post',
        data
    })
}

export function edtDSSettings(data) {
    return request({
        url: '/setting/edtDSSettings',
        method: 'post',
        data
    })
}

export function getDFSettings(data) {
    return request({
        url: '/setting/getDFSettings',
        method: 'post',
        data
    })
}

export function addDFSettings(data) {
    return request({
        url: '/setting/addDFSettings',
        method: 'post',
        data
    })
}

export function delDFSettings(data) {
    return request({
        url: '/setting/delDFSettings',
        method: 'post',
        data
    })
}

export function edtDFSettings(data) {
    return request({
        url: '/setting/edtDFSettings',
        method: 'post',
        data
    })
}

export function getFilters(data) {
    return request({
        url: '/setting/getFilters',
        method: 'post',
        data
    })
}

export function filtersAddOrUpdate(data) {
    return request({
        url: '/setting/filtersAddOrUpdate',
        method: 'post',
        data
    })
}
