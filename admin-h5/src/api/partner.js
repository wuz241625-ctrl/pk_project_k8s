import request from '@/utils/request'

export function exportPartner(data) {
  return request({
    url: '/partner/export',
    method: 'post',
    data
  })
}
export function getPartner(data) {
  return request({
    url: '/partner/getpartner',
    method: 'post',
    data
  })
}
export function getMigrate(data) {
    return request({
        url: '/partner/getMigrate',
        method: 'post',
        data
    })
}
export function migratePartner(data) {
    return request({
        url: '/partner/migratePartner',
        method: 'post',
        data
    })
}

export function addPartner(data) {
  return request({
    url: '/partner/addpartner',
    method: 'post',
    data
  })
}

export function updatePartner(data) {
  return request({
    url: `/partner/updatepartner`,
    method: 'post',
    data
  })
}

export function updatePartnerUnlock(data) {
  return request({
    url: `/partner/updatePartnerUnlock`,
    method: 'post',
    data
  })
}

export function updatePartnerLock(data) {
  return request({
    url: `/partner/updatePartnerLock`,
    method: 'post',
    data
  })
}

export function updateBankType(data) {
    return request({
        url: `/partner/updateBankType`,
        method: 'post',
        data
    })
}

export function addBankType(data) {
    return request({
        url: `/partner/addBankType`,
        method: 'post',
        data
    })
}

export function getPartnerRank(data) {
  return request({
    url: '/partner/getpartnerrank',
    method: 'post',
    data
  })
}

export function getBankRank(data) {
    return request({
        url: '/partner/getBankRank',
        method: 'post',
        data
    })
}

export function getPayment(data) {
  return request({
    url: '/partner/getpayment',
    method: 'post',
    data
  })
}

export function addPayment(data) {
  return request({
    url: '/partner/addpayment',
    method: 'post',
    data
  })
}

export function updatePayment(data) {
  return request({
    url: '/partner/updatepayment',
    method: 'post',
    data
  })
}

export function updatePaymentLimit(data) {
  return request({
    url: '/partner/updatePaymentLimit',
    method: 'post',
    data
  })
}

export function updatePaymentReject(data) {
  return request({
    url: '/partner/updatePaymentReject',
    method: 'post',
    data
  })
}

export function updatePaymentPass(data) {
  return request({
    url: '/partner/updatePaymentPass',
    method: 'post',
    data
  })
}

export function updatePaymentDisenable(data) {
  return request({
    url: '/partner/updatePaymentDisenable',
    method: 'post',
    data
  })
}

export function updatePaymentEnable(data) {
  return request({
    url: '/partner/updatePaymentEnable',
    method: 'post',
    data
  })
}

export function updatePaymentLock(data) {
  return request({
    url: '/partner/updatePaymentLock',
    method: 'post',
    data
  })
}

export function updatePaymentUnlock(data) {
  return request({
    url: '/partner/updatePaymentUnlock',
    method: 'post',
    data
  })
}

export function updatePaymentCorrection(data) {
  return request({
    url: '/partner/updatePaymentCorrection',
    method: 'post',
    data
  })
}

export function updatePaymentCommon(data) {
  return request({
    url: '/partner/updatePaymentCommon',
    method: 'post',
    data
  })
}

export function updatePaymentPri(data) {
  return request({
    url: '/partner/updatePaymentPri',
    method: 'post',
    data
  })
}

export function updatePaymentEdit(data) {
  return request({
    url: '/partner/updatePaymentEdit',
    method: 'post',
    data
  })
}

export function updatePaymentMonitorStatus(data) {
  return request({
    url: '/partner/updatePaymentMonitorStatus',
    method: 'post',
    data
  })
}

export function cancelLimit(data) {
  return request({
    url: '/partner/cancelLimit',
    method: 'post',
    data
  })
}

export function updateBankTypeStatus(data) {
    return request({
        url: '/partner/updateBankTypeStatus',
        method: 'post',
        data
    })
}

export function deleteBankType(data) {
    return request({
        url: '/partner/deleteBankType',
        method: 'post',
        data
    })
}

export function deletePayment(data) {
  return request({
    url: '/partner/deletepayment',
    method: 'post',
    data
  })
}

export function resettingPayment(data) {
    return request({
        url: '/partner/resettingPayment',
        method: 'post',
        data
    })
}

export function batchDisablePayment(data) {
    return request({
        url: '/partner/batchDisablePayment',
        method: 'post',
        data
    })
}

export function getChannel() {
  return request({
    url: '/partner/getchannel',
    method: 'post'
  })
}

export function getBank_type() {
  return request({
    url: '/partner/getbank_type',
    method: 'post'
  })
}


export function getBank_recoed(data) {
  return request({
    url: '/partner/getbank_recoed',
    method: 'post',
    data
  })
}

export function addBank_recoed(data) {
  return request({
    url: '/partner/addbank_recoed',
    method: 'post',
    data
  })
}
export function delBank_recoed(data) {
  return request({
    url: '/partner/delbank_recoed',
    method: 'post',
    data
  })
}


export function get_phonepe(data) {
  return request({
    url: '/partner/get_phonepe',
    method: 'post',
    data
  })
}

export function add_phonepe(data) {
  return request({
    url: '/partner/add_phonepe',
    method: 'post',
    data
  })
}
export function update_phonepe(data) {
  return request({
    url: '/partner/update_phonepe',
    method: 'post',
    data
  })
}
export function del_phonepe(data) {
  return request({
    url: '/partner/del_phonepe',
    method: 'post',
    data
  })
}
export function getBankType(data) {
    return request({
        url: '/partner/getBankType',
        method: 'post',
        data
    })
}

export function getSms(data) {
    return request({
        url: '/partner/getSms',
        method: 'post',
        data
    })
}

export function import_bank_record(data) {
  return request({
      url: '/partner/importBankRecord',
      method: 'post',
      data
  })
}

export function handleClearBalance(data) {
  return request({
      url: '/partner/handleClearBalance',
      method: 'post',
      data
  })
}

export function getBankTypeSetting(data) {
    return request({
        url: '/partner/getBankTypeSetting',
        method: 'post',
        data
    })
}

export function updateBankTypeStatusSetting(data) {
    return request({
        url: '/partner/updateBankTypeStatusSetting',
        method: 'post',
        data
    })
}

export function updateBankTypeSetting(data) {
    return request({
        url: `/partner/updateBankTypeSetting`,
        method: 'post',
        data
    })
}

export function addBankTypeSetting(data) {
    return request({
        url: `/partner/addBankTypeSetting`,
        method: 'post',
        data
    })
}