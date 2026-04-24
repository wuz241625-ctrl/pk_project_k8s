<template>
    <el-card style="margin-bottom:15px;" shadow="never">
        <div v-if="title" slot="header">
            <span style="font-weight:bold;" v-text="title"></span>
            <el-tooltip v-if="message" :content="message" placement="right">
                <i class="el-icon-question"></i>
            </el-tooltip>
            <slot name="header"></slot>
        </div>
        <slot></slot>
    </el-card>
</template>

<script>
export default {
    name: 'ContentWrapper',
    props: {
        title: String,
        message: String
    },
    data() {
        return {}
    }
}
</script>