// src/common/utils/loadComponent.js
const componentMap = {
  ospay: {
    helloComponent: () => import('@/system/ospay/hello.vue')
  },
  '789pay': {
    helloComponent: () => import('@/system/789pay/hello.vue')
  },
  common: {
    helloComponent: () => import('@/system/common/hello.vue')
  }
}
export async function loadSystemComponent(componentName, fallbackName) {
  const system = process.env.VUE_APP_SYSTEM || 'common'
  let comp = null
  try {
    comp = componentMap[system][componentName]
  } catch (error) {
    comp = componentMap.common[fallbackName]
  }
  return comp()
}
