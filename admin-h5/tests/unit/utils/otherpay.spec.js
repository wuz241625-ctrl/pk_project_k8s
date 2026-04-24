import { getOtherPayOptionLabel } from '@/utils/otherpay'

describe('getOtherPayOptionLabel', () => {
  it('优先使用后端返回的 label', () => {
    expect(getOtherPayOptionLabel({
      id: 25,
      name: 'easypay',
      label: 'easypay | 165338898 | 1203411 | #25'
    })).toBe('easypay | 165338898 | 1203411 | #25')
  })

  it('在没有 label 时回退到 name', () => {
    expect(getOtherPayOptionLabel({
      id: 25,
      name: 'easypay'
    })).toBe('easypay')
  })
})
