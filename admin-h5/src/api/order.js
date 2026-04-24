import request from '@/utils/request'

export function getOrderds(data) {
    return request({
        url: '/order/getorderds',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getDSMerchantFinishOrProcessing(data) {
    return request({
        url: '/order/getDSMerchantFinishOrProcessing',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getorderdscd(data) {
    return request({
        url: '/order/getorderdscd',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getDSCDProcessing(data) {
    return request({
        url: '/order/getDSCDProcessing',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getCdType() {
    return request({
        url: '/order/getCdType',
        method: 'post'
    })
}

export function handleOrder(data) {
    return request({
        url: '/order/handleorder',
        method: 'post',
        data
    })
}
export function handleOrderFromThird(data) {
    return request({
        url: '/order/handleOrderFromThird',
        method: 'post',
        data
    })
}

export function addDsToCd(data) {
    return request({
        url: '/order/addDsToCd',
        method: 'post',
        data
    })
}

export function updateCdAudit(data) {
    return request({
        url: '/order/updateCdAudit',
        method: 'post',
        data
    })
}
export function updateCdConfirm(data) {
    return request({
        url: '/order/updateCdConfirm',
        method: 'post',
        data
    })
}
export function updateNoConfirm(data) {
    return request({
        url: '/order/updateNoConfirm',
        method: 'post',
        data
    })
}

export function handleNotifyds(data) {
    return request({
        url: '/order/handlenotifyds',
        method: 'post',
        data
    })
}

export function confirmSplitOrder(data) {
    return request({
        url: '/order/confirmSplitOrder',
        method: 'post',
        data
    })
}

export function getOrderdf(data) {
    return request({
        url: '/order/getorderdf',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getOrderDfSplit(data) {
    return request({
        url: '/order/getOrderDfSplit',
        method: 'post',
        data
    })
}

export function getDFMerchantFinishOrProcessing(data) {
    return request({
        url: '/order/getDFMerchantFinishOrProcessing',
        method: 'post',
        timeout: 60 * 2 * 1000, // 某些导出excel文件的接口超时设置长点
        data
    })
}

export function getThirdPays(data) {
    return request({
        url: '/order/getThirdPays',
        method: 'post',
        data
    })
}

export function handleBatchThirdpay(data) {
    return request({
        url: '/order/handleBatchThirdpay',
        method: 'post',
        data
    })
}

export function handleBatchOrderdf(data) {
    return request({
        url: '/order/handleBatchOrderdf',
        method: 'post',
        data
    })
}

export function saveHuizhi(data) {
    return request({
        url: '/order/saveHuizhi',
        method: 'post',
        data
    })
}


/* 代付改派权限分离
确认，上传凭证，改派，指派 全部分开
export function handleOrderdf(data) {
    return request({
        url: '/order/handleorderdf',
        method: 'post',
        data
    })
}
 */
export function handleOrderdfType1(data) {
    return request({
        url: '/order/handleOrderdfType1',
        method: 'post',
        data
    })
}

export function handleOrderdfType2(data) {
    return request({
        url: '/order/handleOrderdfType2',
        method: 'post',
        data
    })
}

export function handleOrderdfType3(data) {
    return request({
        url: '/order/handleOrderdfType3',
        method: 'post',
        data
    })
}

export function handleOrderdfType4(data) {
    return request({
        url: '/order/handleOrderdfType4',
        method: 'post',
        data
    })
}

export function cancelOrderdf(data) {
    return request({
        url: '/order/cancelorderdf',
        method: 'post',
        data
    })
}

export function handleNotifydf(data) {
    return request({
        url: '/order/handlenotifydf',
        method: 'post',
        data
    })
}

export function getPartnerTransfer(data) {
    return request({
        url: '/order/getpartnertransfer',
        method: 'post',
        data
    })
}

export function handlePartnerTransfer(data) {
    return request({
        url: '/order/handlepartnertransfer',
        method: 'post',
        data
    })
}

export function getMerchantTransfer(data) {
    return request({
        url: '/order/getmerchanttransfer',
        method: 'post',
        data
    })
}

export function handleMerchantTransfer(data) {
    return request({
        url: '/order/handlemerchanttransfer',
        method: 'post',
        data
    })
}

export function uploadReceiptBatch(data) {
    return request({
        url: '/order/uploadreceiptbatch',
        method: 'post',
        data
    })
}

export function getBankTypeByPaymentId(data) {
    return request({
        url: '/order/getBankTypeByPaymentId',
        method: 'post',
        data
    })
}

export function importBankWithdrawal(data = {}) {
    return request({
        url: '/order/importBankWithdrawal',
        method: 'post',
        data
    })
}

export function getBankWithdrawal(data = {}) {
    return request({
        url: '/order/getBankWithdrawal',
        method: 'post',
        data
    })
}

export function handleOrderdfRevert(data) {
    return request({
        url: '/order/handleOrderdfRevert',
        method: 'post',
        data
    })
}

export function releaseOrderdf(data) {
    return request({
        url: '/order/releaseOrderdf',
        method: 'post',
        data
    })
}

// 自动代付监控相关API
export function getAutoPaymentStats() {
    return request({
        url: '/api/auto-payout/stats',
        method: 'get'
    })
}

export function getAutoPaymentOrders(params) {
    return request({
        url: '/api/auto-payout/orders',
        method: 'get',
        params
    })
}

export function toggleAutoPayment(data) {
    return request({
        url: '/api/auto-payout/toggle',
        method: 'post',
        data
    })
}

export function paymentIdCooldown() {
    return request({
        url: '/api/auto-payout/payment-id-cooldown',
        method: 'get'
    })
}

export function setOrderCooldownConfig(data) {
    return request({
        url: '/api/auto-payout/order-cooldown-config',
        method: 'post',
        data
    })
}

export function orderCooldownConfig() {
    return request({
        url: '/api/auto-payout/order-cooldown-config',
        method: 'get'
    })
}

export function setPaymentIdCooldown(params) {
    return request({
        url: '/api/auto-payout/payment-id-cooldown',
        method: 'post',
        params
    })
}


export function getAutoPaymentToggleStatus() {
    return request({
        url: '/api/auto-payout/toggle',
        method: 'get'
    })
}

export function emergencyStopAutoPayment() {
    return request({
        url: '/api/auto-payout/emergency-stop',
        method: 'post'
    })
}

export function getAutoPaymentMonitor() {
    return request({
        url: '/api/auto-payout/monitor',
        method: 'get'
    })
}

// 获取订单详情和操作日志
export function getAutoPaymentOrderDetail(params) {
    return request({
        url: '/api/auto-payout/order-detail',
        method: 'get',
        params
    })
}
