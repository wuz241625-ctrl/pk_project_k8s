import request from '@/utils/request'

export function getLogs(params) {
    return request({
        url: '/system/operationlog',
        method: 'get',
        params
    })
}