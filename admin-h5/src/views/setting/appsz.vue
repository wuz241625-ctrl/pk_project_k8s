<template>
    <div class="app-container">
        <el-form :model="appszData" label-width="180px" label-position="left">
            <el-form-item :label="$t('method.app.name')" style="width: 500px;">
                <el-input v-model="appszData.name" :placeholder="$t('method.app.placeholder.name')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.versionCode')">
                <el-input v-model="appszData.versionCode" :placeholder="$t('method.app.placeholder.versionCode')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.version')">
                <el-input v-model="appszData.version" :placeholder="$t('method.app.placeholder.version')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.domainName')">
                <el-input v-model="appszData.domainName" :placeholder="$t('method.app.placeholder.domainName')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.fileUrl')">
                <el-input v-model="appszData.fileUrl" :placeholder="$t('method.app.placeholder.fileUrl')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.download')">
                <el-input v-model="appszData.download" :placeholder="$t('method.app.placeholder.download')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.customerService')">
                <el-input v-model="appszData.customerService" :placeholder="$t('method.app.placeholder.customerService')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.isForce')">
                <el-switch v-model="appszData.isForce" :active-value="1" :inactive-value="0" active-color="#13ce66" />
            </el-form-item>
            <el-form-item :label="$t('method.app.describe')">
                <el-input v-model="appszData.describe" :placeholder="$t('method.app.placeholder.describe')" />
            </el-form-item>
            <el-form-item :label="$t('method.app.isSilence')">
                <el-switch v-model="appszData.isSilence" :active-value="1" :inactive-value="0" active-color="#13ce66" />
            </el-form-item>
            <el-form-item :label="$t('method.app.packageType')">
                <el-switch v-model="appszData.packageType" :active-value="1" :inactive-value="0" active-color="#13ce66" />
            </el-form-item>
            <el-form-item :label="$t('method.app.google')" style="width: 300px;">
                <el-input v-model="appszData.google" :placeholder="$t('method.app.placeholder.google')" />
            </el-form-item>
            <el-button type="danger" class="confButton" @click="confirmRole">{{ $t('method.app.save') }}</el-button>
        </el-form>
    </div>
</template>

<script>
import {
    getAppsz,
    updateAppsz,
    getWeight,
    updateWeight,
} from '@/api/setting'
export default {
    data() {
        return {
            appszData: {},
            weightData: {},
        }
    },
    created() {
        this.getData()
        this.getWeight()
    },
    methods: {
        // 获取设置
        async getData() {
            const res = await getAppsz()
            this.appszData = res.data
        },
        // 获取权重
        async getWeight() {
            const res = await getWeight()
            let sum = 0;
            for (let item of res.data) {
                // 确保 payment_numbers 和 weight 是数字类型，以防 NaN 错误
                let payment_numbers = Number(item.payment_numbers);
                let weight = Number(item.weight);

                // 计算 payment_numbers 和 weight 的乘积，然后累加到总和
                if (!isNaN(payment_numbers) && !isNaN(weight)) {
                    sum += payment_numbers * weight;
                }
            }
            console.log(sum);
            for (let item of res.data) {
                item.all_code_probability = ((item.weight*item.payment_numbers)/sum*100).toFixed(2)
                item.one_code_probability = (item.weight/sum*100).toFixed(2)
            }

            this.weightData = res.data
        },
        /* 保存 */
        async confirmRole() {
            if (isNaN(this.appszData.google) || this.appszData.google.length < 6) {
                const message = this.$t('method.roleSave.invalidGoogle');
                this.$message({
                    type: 'warning',
                    message: message
                });
                return;
            }
            // 获取isForce
            this.appszData.isForce = this.appszData.isForce ? 1 : 0;
            // 获取isSilence
            this.appszData.isSilence = this.appszData.isSilence ? 1 : 0;
            // 获取packageType
            this.appszData.packageType = this.appszData.packageType ? 1 : 0;
            try {
                await updateAppsz(this.appszData);
            } catch (err) {
                return;
            }
            this.$notify({
                title: this.$t('method.roleSave.saveSuccessTitle'),
                dangerouslyUseHTMLString: true,
                type: 'success'
            });
        },

        handleInput(item, weightData) {
            let value = parseFloat(item.weight);
            if (isNaN(value)) {
                item.weight = 1;
                value = 0;
            }
            if (Math.floor(value) < 1 || value <= 0 || isNaN(value)) {
                this.$confirm(this.$t('method.weightInput.invalidValue'), this.$t('method.weightInput.title'), {
                    type: 'warning',
                    confirmButtonText: this.$t('method.confirm'),
                    cancelButtonText: this.$t('method.cancel')
                });
                item.weight = Math.abs(item.weight);
                return;
            }

            let sum = 0;
            for (let item of weightData) {
                let payment_numbers = Number(item.payment_numbers);
                let weight = Number(item.weight);

                if (!isNaN(payment_numbers) && !isNaN(weight)) {
                    sum += payment_numbers * weight;
                }
            }
            for (let item of weightData) {
                item.all_code_probability = ((item.weight * item.payment_numbers) / sum * 100).toFixed(2);
                item.one_code_probability = (item.weight / sum * 100).toFixed(2);
            }
        },

        // 保存权重
        async confirmWeight() {
            if (isNaN(this.weightData.google) || this.weightData.google.length < 6) {
                const message = this.$t('method.weightSave.invalidGoogle');
                this.$message({
                    type: 'warning',
                    message: message
                });
                return;
            }
            try {
                const data = { "data": this.weightData, "google": this.weightData.google };
                await updateWeight(data);
            } catch (err) {
                return;
            }
            this.$notify({
                title: this.$t('method.weightSave.saveSuccessTitle'),
                dangerouslyUseHTMLString: true,
                type: 'success'
            });
        },
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
