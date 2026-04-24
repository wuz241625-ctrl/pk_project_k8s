<template>
  <div class="app-container">
    <el-form :model="ipData" label-width="100px" label-position="left">
      <el-form-item :label="$t('apihmd.form.ipList')">
        <el-input v-model="ipData.ipString" :autosize="{ minRows: 8, maxRows: 20}" type="textarea" :placeholder="$t('apihmd.form.ipPlaceholder')" />
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
        getIP,
        updateIP
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
                this.ipData.name = ipname
                const res = await getIP(this.ipData)
                this.ipData.ipString = res.data[ipname]
            },
            /* 保存 */
    async confirmRole() {
        // 检查 ipData.name 是否为 "api_ip_b" 且 IP 包含 127.0.0.* 段
        // apihmd ：黑名单(api_ip_b)    xtbmd： 白名单(sys_ip_w)
        if (this.ipData.name === 'api_ip_b' && this.ipData.ipString.split(",").some(ip => ip.trim().startsWith("127.0.0."))) {
            this.$message({
                type: 'warning',
                message: this.$t('method.confirmRole.ipWarning') // 这里可以换成对应的提示信息
            });
            return;
        }

        // 获取谷歌验证码长度和是否为数字
        if (this.ipData.google.length < 6 || isNaN(this.ipData.google)) {
            this.$message({
                type: 'warning',
                message: this.$t('method.confirmRole.googleCodeWarning')
            });
            return;
        }
        try {
            await updateIP(this.ipData);
        } catch (err) {
            return;
        }
        this.$notify({
            title: this.$t('method.confirmRole.saveSuccessTitle'),
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