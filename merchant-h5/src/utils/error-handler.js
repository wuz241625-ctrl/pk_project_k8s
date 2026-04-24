import i18n from '../i18n';

export function getErrorMessage(code) {
  // Access the error message from i18n messages based on the error code
  // return i18n.t(`${code}`, { default: i18n.t(`${msg.code}`) });
  return i18n.t(`msg.${code}`, { defaultValue: 'Unknown error' });
}
