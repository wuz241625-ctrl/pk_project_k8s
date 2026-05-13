export function isValidPartnerPayPassword(password) {
    if (!password) {
        return true
    }
    return /^\d{6}$/.test(String(password))
}
