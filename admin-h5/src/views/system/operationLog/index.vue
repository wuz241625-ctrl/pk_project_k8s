<template>
    <ContentWrapper>
        <el-form :model="searchForm" ref="searchFormRef" inline label-position="left" label-width="5em">
            <el-form-item :label="$t('operationLog.search.createTime')" prop="create_time">
                <el-date-picker v-model="searchForm.create_time" size="small" value-format="yyyy-MM-dd HH:mm:ss" type="datetimerange"
                                :range-separator="$t('search.dateRangeSeparator')" :start-placeholder="$t('search.startDate')"
                                :end-placeholder="$t('search.endDate')" />
            </el-form-item>
            <el-form-item :label="$t('operationLog.search.module')" prop="module">
                <el-select v-model="searchForm.module" clearable size="small" :placeholder="$t('search.selectPlaceholder')">
                    <el-option :label="$t('routes.codeMerchantManagement.list.title')" :value="$t('routes.codeMerchantManagement.list.title')"></el-option>
                </el-select>
            </el-form-item>
            <el-form-item :label="$t('operationLog.search.eventType')" prop="event_type">
                <el-select v-model="searchForm.event_type" clearable size="small" :placeholder="$t('search.selectPlaceholder')">
                    <el-option :label="eventTypes['create']" value="create"></el-option>
                    <el-option :label="eventTypes['update']" value="update"></el-option>
                    <el-option :label="eventTypes['delete']" value="delete"></el-option>
                    <el-option :label="eventTypes['read']" value="read"></el-option>
                    <el-option :label="eventTypes['download']" value="download"></el-option>
                </el-select>
            </el-form-item>
            <el-form-item :label="$t('operationLog.search.userName')" prop="uid">
                <el-select v-model="searchForm.uid" clearable filterable size="small" :placeholder="$t('search.selectPlaceholder')">
                    <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
            </el-form-item>
            <el-form-item>
                <el-button @click="loadData" type="primary" plain size="small" icon="el-icon-search">{{ $t('search.query') }}</el-button>
                <el-button @click="resetSearchForm" plain size="small" icon="el-icon-refresh">{{ $t('search.reset') }}</el-button>
            </el-form-item>
        </el-form>
        <el-table
            :data="list"
            style="width: 100%;margin-top:30px;"
            border
            stripe
            :header-cell-style="{background:'#DCDFE6', color:'#606266'}"
        >
            <el-table-column prop="id" label="ID" align="center"/>
            <el-table-column prop="user_name" :label="$t('operationLog.search.userName')" align="center"/>
            <el-table-column prop="utype" :label="$t('operationLog.table.utype')" align="center"/>
            <el-table-column prop="user_ip" label="IP" align="center"/>
            <el-table-column prop="event_type" :label="$t('operationLog.search.eventType')" align="center" :formatter="(r,c,v) => eventTypes[v]"/>
            <el-table-column prop="module" :label="$t('operationLog.search.module')" align="center"/>
            <el-table-column prop="event_desc" :label="$t('operationLog.table.eventDesc')" align="center"/>
            <el-table-column prop="event_content" :label="$t('operationLog.table.eventContent')" align="center"/>
            <el-table-column prop="event_result" :label="$t('operationLog.table.eventResult')" align="center"/>
            <el-table-column prop="create_time" :label="$t('operationLog.search.createTime')" align="center"/>
        </el-table>
        <Pagination v-bind:page.sync="searchForm.page" v-bind:size.sync="searchForm.size" :total="total" @pagination="loadData" />
    </ContentWrapper>
</template>

<script>
import { getMembers } from '@/api/permission'
import { getLogs } from '@/api/system/operationLog'
export default {
    data() {
        return {
            eventTypes: {
                create: this.$t('operationLog.enum.create'),
                update: this.$t('operationLog.enum.update'),
                delete: this.$t('operationLog.enum.delete'),
                read: this.$t('operationLog.enum.read'),
                download: this.$t('operationLog.enum.download'),
            },
            users: [],
            searchForm: {
                page: 1,
                size: 10,
                create_time: undefined,
                module: undefined,
                event_type: undefined,
                uid: undefined,
            },
            list: [],
            total: 0
        }
    },
    mounted() {
        this.loadData()
        this.loadAllAdmins()
    },
    methods: {
        clickLoad() {
            this.loadData()
        },
        loadAllAdmins() {
            getMembers()
            .then(res => {
                this.users = res.data
            })
        },
        loadData() {
            const { create_time } = this.searchForm
            const params = {
                ...this.searchForm
            }
            // if (create_time) {
            //     params.create_time = create_time.join(',')
            // }
            getLogs(params).then(res => {
                this.list = res.data.list
                this.total = res.data.total
            })
        },
        resetSearchForm() {
            this.$nextTick(() => {
                this.$refs?.searchFormRef.resetFields()
            })
            this.loadData()
        }
    }
}
</script>
