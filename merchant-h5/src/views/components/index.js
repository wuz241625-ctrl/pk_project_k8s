import BaseSearch from './BaseSearch'

const array = [BaseSearch]

const baseComponents = {
  install(vue) {
    for (let i = 0; i < array.length; i++) {
      vue.component(array[i].name, array[i])
    }
  }
}

export default baseComponents
