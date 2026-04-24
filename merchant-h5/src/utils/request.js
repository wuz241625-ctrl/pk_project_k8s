import axios from 'axios'
import { Message } from 'element-ui'
import Cookies from 'js-cookie'
import { getErrorMessage } from './error-handler';

// create an axios instance
const service = axios.create({
  baseURL: process.env.VUE_APP_BASE_API, // url = base url + request url
  withCredentials: true, // send cookies when cross-domain requests
  timeout: 60000 // request timeout
})

// request interceptor
service.interceptors.request.use(
  config => {
    // xsrf 验证
    config.headers['X-Csrftoken'] = Cookies.get('_xsrf')
    return config
  },
  error => {
    console.log(error) // for debug
    return Promise.reject(error)
  }
)

// response interceptor
service.interceptors.response.use(
  response => {
    const res = response.data
    console.log(res)
    if (res.code !== 20000 && res.code !== 0) {
      const errorMessage = getErrorMessage(res.code);
      Message({
        message: errorMessage || '异常错误',
        type: 'error',
        duration: 5 * 1000
      })
      return Promise.reject(new Error(res.message || 'Error'))
    } else {
      return res
    }
  },
  error => {
    var msg = error.message
    // 403显示具体原因
    if (error.response.status === 403) {
      msg = error.response.data.split('<title>')[1].split('</title>')[0]
    }
    // 默认403或500则返回登录
    if (msg === '403: Forbidden') {
      msg = '请重新登录'
    }
    Message({
      message: msg,
      type: 'error',
      duration: 5 * 1000
    })
    return Promise.reject(error)
  }
)

export default service
