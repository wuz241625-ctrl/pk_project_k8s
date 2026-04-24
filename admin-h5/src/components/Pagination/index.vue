<template>
    <div class="block" style="margin-top: 20px;">
        <el-pagination background :current-page="page" :page-sizes="[10, 20, 50, 100]" :page-size="size"
            layout="total, sizes, prev, pager, next, jumper" :total="total" @size-change="handleSizeChange"
            @current-change="handleCurrentChange" />
    </div>
</template>

<script>
export default {
    name: 'Pagination',
    props: {
        page: {
            type: Number,
            default: 1
        },
        size: {
            type: Number,
            default: 10
        },
        total: {
            type: Number,
            default: 0
        }

    },
    data() {
        return {

        }
    },
    methods: {
        handleCurrentChange(page) {
            this.$emit('update:page', page)
            this.$emit('pagination', { page, size: this.size })
        },
        handleSizeChange(val) {
            const page = this.page * val > this.total ? 1 : val
            this.$emit('update:size', val)
            this.$emit('pagination', { page, size: val })
        }
    }
}
</script>