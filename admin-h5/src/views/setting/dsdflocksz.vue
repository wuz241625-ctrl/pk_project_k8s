<template>
    <div class="app-container">
        <el-form :model="lockSettings" label-width="180px" label-position="left">
            <el-form-item :label="$t('method.dsdflock.switch')">
                <el-switch v-model="lockSettings.switch" :active-value="1" :inactive-value="0" active-color="#13ce66" />
            </el-form-item>
            <el-form-item :label="$t('method.dsdflock.start_time')" required>
                <el-time-picker v-model="lockSettings.start_time" :placeholder="$t('method.dsdflock.start_time_placeholder')" format="HH:mm" />
            </el-form-item>
            <el-form-item :label="$t('method.dsdflock.end_time')" required>
                <el-time-picker v-model="lockSettings.end_time" :placeholder="$t('method.dsdflock.end_time_placeholder')" format="HH:mm" />
            </el-form-item>
            <el-form-item :label="$t('method.dsdflock.google')" required>
                <el-input v-model="lockSettings.google" :placeholder="$t('method.dsdflock.google_placeholder')" />
            </el-form-item>
            <el-button type="danger" class="confButton" @click="saveSettings">{{ $t('method.dsdflock.save') }}</el-button>
        </el-form>
    </div>
</template>

<script>
import { getDsdfLockSettings, updateDsdfLockSettings } from '@/api/setting'

export default {
    data() {
        return {
            lockSettings: {
                switch: 0,
                start_time: '',
                end_time: '',
                google: ''
            }
        }
    },
    created() {
        this.fetchLockSettings()
    },
    methods: {
        async fetchLockSettings() {
            const res = await getDsdfLockSettings()
            const parseTime = (timeStr) => {
                const [hours, minutes] = timeStr.split(':');
                const date = new Date();
                date.setHours(parseInt(hours), parseInt(minutes), 0, 0);
                return date;
            };
            if(res.data){
                this.lockSettings = res.data
                this.lockSettings.start_time = parseTime(this.lockSettings.start_time);
                this.lockSettings.end_time = parseTime(this.lockSettings.end_time);
            }
        },
        async saveSettings() {
            if (!this.lockSettings.google || this.lockSettings.google.length < 6) {
                this.$message({
                    type: 'warning',
                    message: this.$t('method.dsdflock.invalidGoogle')
                })
                return
            }


            const formatTime = (date) => {
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${hours}:${minutes}`;
            };
            const obj = { ...this.lockSettings }
            obj.start_time = formatTime(this.lockSettings.start_time);
            obj.end_time = formatTime(this.lockSettings.end_time);

            console.log("this.lockSettings:",this.lockSettings)
            try {
                await updateDsdfLockSettings(obj)
                this.$notify({
                    title: this.$t('method.dsdflock.saveSuccess'),
                    type: 'success'
                })
            } catch (error) {
                console.error(error)
            }
        }
    }
}
</script>

<style lang="scss" scoped>
.app-container {
    .confButton {
        margin-left: 100px;
    }
}
</style>
