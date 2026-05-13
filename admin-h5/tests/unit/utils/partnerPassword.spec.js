import { isValidPartnerPayPassword } from '@/utils/partnerPassword'

describe('isValidPartnerPayPassword', () => {
    it('允许空支付密码，避免编辑时强制重置', () => {
        expect(isValidPartnerPayPassword('')).toBe(true)
        expect(isValidPartnerPayPassword(null)).toBe(true)
        expect(isValidPartnerPayPassword(undefined)).toBe(true)
    })

    it('只允许 6 位数字支付密码', () => {
        expect(isValidPartnerPayPassword('123456')).toBe(true)
        expect(isValidPartnerPayPassword('000000')).toBe(true)
    })

    it('拒绝非 6 位数字支付密码', () => {
        expect(isValidPartnerPayPassword('12345')).toBe(false)
        expect(isValidPartnerPayPassword('1234567')).toBe(false)
        expect(isValidPartnerPayPassword('12a456')).toBe(false)
        expect(isValidPartnerPayPassword('12345!')).toBe(false)
    })
})
