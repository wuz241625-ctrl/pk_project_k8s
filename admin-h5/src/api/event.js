import request from '@/utils/request'

export function getevents(data) {
  return request({
    url: '/event/getevent',
    method: 'post',
    data
  })
}

export function addevent(data) {
  return request({
    url: '/event/addevent',
    method: 'post',
    data
  })
}

export function updateevent(data) {
  return request({
    url: `/event/updateevent`,
    method: 'post',
    data
  })
}

export function deleteevent(data) {
  return request({
    url: `/event/deleteevent`,
    method: 'post',
    data
  })
}


export function getPoolLogs(data) {
    return request({
        url: '/event/getPoolLogs',
        method: 'post',
        data
    })
}

export function getPoolAmount() {
    return request({
        url: '/event/getPoolAmount',
        method: 'post'
    })
}

export function addPoolAmount(data) {
    return request({
        url: '/event/addPoolAmount',
        method: 'post',
        data
    })
}


export function getEventBeginnerProcess(data) {
  return request({
      url: '/event/getEventBeginnerProcess',
      method: 'post',
      data
  })
}
