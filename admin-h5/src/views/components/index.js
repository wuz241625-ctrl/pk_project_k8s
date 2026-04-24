import BaseSearch from './BaseSearch'
import ContentWrapper from '@/components/ContentWrapper/index.vue'
import Pagination from '@/components/Pagination/index.vue'
const array = [BaseSearch,ContentWrapper,Pagination]

const baseComponents = {
  install(vue) {
    for (let i = 0; i < array.length; i++) {
      vue.component(array[i].name, array[i])
    }
  }
}

export default baseComponents
