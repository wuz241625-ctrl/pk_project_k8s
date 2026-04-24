import request from '@/utils/request'

export function getMessageList(data) {
    return request({
        url: '/message/list',
        method: 'post',
        data
    })
}

export function addMessage(data) {
    return request({
        url: '/message/add',
        method: 'post',
        data
    })
}

export function deleteMessage(data) {
    return request({
        url: '/message/delete',
        method: 'post',
        data
    })
}

export function publishMessage(data) {
    return request({
        url: '/message/publish',
        method: 'post',
        data
    })
}

export function updateMessage(data) {
    return request({
        url: '/message/update',
        method: 'post',
        data
    })
} 