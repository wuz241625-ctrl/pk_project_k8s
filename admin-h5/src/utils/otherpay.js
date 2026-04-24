export function getOtherPayOptionLabel(option) {
  if (!option) {
    return ''
  }

  return option.label || option.name || ''
}
