<template>
  <div class="app-container">
    <el-form :model="ipData" label-width="100px" label-position="left">
      <el-form-item label="IP名单:">
        <el-input
          v-model="ipData.ipString"
          :autosize="{ minRows: 8, maxRows: 20}"
          type="textarea"
          placeholder="请输入IP地址,多个IP地址请使用','符号分割,不填写则不限制IP"
        />
      </el-form-item>

      <el-form-item label="谷歌验证码" style="width: 300px;">
        <el-input v-model="ipData.google" placeholder="请输入谷歌验证码" />
      </el-form-item>

      <el-button type="danger" class="confButton" @click="confirmRole">保存</el-button>

    </el-form>
  </div>
</template>

<script>
import {
    getIP,
    updateIP
} from '@/api/setting'

const defaultipData = {
    ipString: '',
    google: ''
}

export default {
    data() {
        return {
            ipData: Object.assign({}, defaultipData)
        }
    },
    created() {
        this.getIptable()
    },
    methods: {
        // 获取IP地址列表
        async getIptable(ipname) {
            const res = await getIP()
            this.ipData.ipString = res.data.ip
        },
        /* 保存*/
        async confirmRole() {
            if (this.ipData.google.length < 6 || isNaN(this.ipData.google)) {
                var message = '请输入6位数字谷歌验证码'
                this.$message({
                    type: 'warning',
                    message: message
                })
                return
            }
            try {
                await updateIP(this.ipData)
            } catch (err) {
                return
            }
            this.$notify({
                title: '保存成功',
                dangerouslyUseHTMLString: true,
                type: 'success'
            })
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
