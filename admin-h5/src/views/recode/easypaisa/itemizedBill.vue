<template>
    <div class="ep_jcb_record">
        <el-tabs v-model="activeName" @tab-click="handleClick">
            <el-tab-pane label="easypaisa" name="easypaisa">
                <easypaisa/>
            </el-tab-pane>
            <el-tab-pane label="jazzpaisa" name="jazzpaisa">
                <jazzcash/>
            </el-tab-pane>
        </el-tabs>
    </div>
</template>

<script>
import easypaisa from '@/views/recode/easypaisa/easypaisa.vue'
import jazzcash from '@/views/recode/easypaisa/jazzcash.vue'



export default {
    name: 'record',
    components: {
        easypaisa,
        jazzcash
    },
    data() {
        return {
            activeName:'easypaisa'
        }
    },
    created() {
        // this.getData()
    },
    methods: {
        handleClick(){

        }
    }
}
</script>
<style scoped>
.ep_jcb_record{
    margin: 20px;
}
</style>
