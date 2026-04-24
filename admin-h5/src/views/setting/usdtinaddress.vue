<template>
  <div class="app-container">
    <el-form :model="ipData" label-width="100px" label-position="left">
      <el-form-item label="usdt转入地址">
        <el-input v-model="ipData.usdt_received_address" :autosize="{ minRows: 8, maxRows: 20}" type="textarea" placeholder="请输入usdt转入地址" />
      </el-form-item>

      <el-form-item :label="$t('apihmd.form.googleCode')" style="width: 300px;">
        <el-input v-model="ipData.google" :placeholder="$t('apihmd.form.googleCodePlaceholder')" />
      </el-form-item>

      <el-button type="danger" class="confButton" @click="confirmRole">{{ $t('apihmd.form.save') }}</el-button>
    </el-form>
  </div>
</template>

<script>
    import {
        getUsdtTransferAddress,
        updateUsdtTransferAddress
    } from '@/api/setting'
    import router from '@/router'

    const defaultipData = {
        ipString: '',
        google: ''
    }

    export default {
        data() {
            return {
                ipData: Object.assign({}, defaultipData),
                ipnames: {
                    'xtbmd': 'sys_ip_w',
                    'apihmd': 'api_ip_b'
                }
            }
        },
        created() {
            this.getIptable(this.ipnames[router.currentRoute.name])
        },
        methods: {
            // 获取IP地址列表
            async getIptable(ipname) {
                const res = await getUsdtTransferAddress()
                this.ipData = res.data
            },
            /* 保存 */
    async confirmRole() {
        // 获取谷歌验证码长度和是否为数字
        if (!this.ipData.google || String(this.ipData.google).length < 6 || isNaN(this.ipData.google)) {
            this.$message({
                type: 'warning',
                message: this.$t('method.confirmRole.googleCodeWarning')
            });
            return;
        }

        try {
            await updateUsdtTransferAddress(this.ipData);
        } catch (err) {
            return;
        }
        this.$notify({
            title: '保存成功',
            dangerouslyUseHTMLString: true,
            type: 'success'
        });
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
