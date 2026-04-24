import request from '@/utils/request'

export function getChanceList(data) {
  return request({
    url: '/event/getLotteryChance',
    method: 'post',
    data
  })
}

export function addChance(data) {
  return request({
    url: '/event/addLotteryChance',
    method: 'post',
    data
  })
}

export function getChanceLog(data) {
  return request({
    url: '/event/getLotteryChanceLog',
    method: 'post',
    data
  })
} 