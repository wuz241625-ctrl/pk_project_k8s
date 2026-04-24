import request from '@/utils/request'

export function geteventrules(data) {
  return request({
    url: '/eventrule/getEventrule',
    method: 'post',
    data
  })
}

export function addeventrule(data) {
  return request({
    url: '/eventrule/addeventrule',
    method: 'post',
    data
  })
}

export function updateeventrule(data) {
  return request({
    url: `/eventrule/updateeventrule`,
    method: 'post',
    data
  })
}

export function deleteeventrule(data) {
  return request({
    url: `/eventrule/deleteeventrule`,
    method: 'post',
    data
  })
}

export function geteventlogs(data) {
  return request({
    url: '/eventlogs/getEventLogs',
    method: 'post',
    data
  })
}

