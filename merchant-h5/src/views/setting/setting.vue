<template>

  <div class="app-container">
    <el-form :model="info" label-width="80px" label-position="left">
      <el-form-item :label="$t('setting.balance')"  label-width="180px" >
        <el-input v-model="info.balance" :disabled="true" style="max-width: 282px;" />
      </el-form-item>
<!--      <el-form-item label="商户密钥">-->
<!--        <el-input v-model="info.mc_key" :disabled="true" style="max-width: 282px;" />-->
<!--      </el-form-item>-->
      <el-form-item :label="$t('setting.frozen_amount')"  label-width="180px" >
        <el-input v-model="info.balance_frozen" :disabled="true" style="max-width: 282px;" />
      </el-form-item>
<!--      <el-form-item label="代付费率">-->
<!--        <el-input v-model="info.rate_df" :disabled="true" style="max-width: 282px;" />-->
<!--      </el-form-item>-->
<!--      <el-form-item label="代付单笔">-->
<!--        <el-input v-model="info.fee_df" :disabled="true" style="max-width: 282px;" />-->
<!--      </el-form-item>-->
<!--      <el-form-item label="谷歌密钥">-->
<!--        <el-input v-model="gg_key" :disabled="true" style="max-width: 282px;" />-->
<!--        <el-button-->
<!--          style="margin-left: 16px;"-->
<!--          type="primary"-->
<!--          size="small"-->
<!--          @click="handlecheckGg"-->
<!--        >查看密钥</el-button>-->
<!--      </el-form-item>-->
      <el-button style="margin-left: 16px;" type="warning" size="small" @click="handleResetPw">{{$t('setting.reset_password')}}</el-button>
<!--      <el-button style="margin-left: 16px;" type="danger" size="small" @click="handleResetGg">重置密钥</el-button>-->
    </el-form>
    <!-- 弹窗-->
    <el-dialog :visible.sync="dialogVisible" :title="$t('setting.reset_password')">
      <el-form :model="newpw" label-width="180px" label-position="left">
        <el-form-item :label="$t('setting.google_key')">
          <el-input v-model="newpw.google" :placeholder="$t('setting.enter_google_code')" style="max-width: 400px;" />
        </el-form-item>
        <el-tooltip
          v-model="capsTooltip"
          content="Caps lock is On"
          placement="right"
          manual
          style="max-width: 282px;"
        >
          <el-form-item :label="$t('setting.new_password')">
            <div style="width:400px;">
                <el-input
                :key="passwordType"
                ref="password"
                v-model="newpw.new_password"
                :type="passwordType"
                :placeholder="$t('setting.password')"
                tabindex="2"
                autocomplete="on"
                @keyup.native="checkCapslock"
                @blur="capsTooltip = false"
                @keyup.enter.native="handleLogin"
                />
                <span class="show-pwd" @click="showPwd">
                <svg-icon :icon-class="passwordType === 'password' ? 'eye' : 'eye-open'" />
                </span>
            </div>
          </el-form-item>
        </el-tooltip>
      </el-form>
      <div style="text-align:right;">
        <el-button type="primary" @click="dialogVisible=false">{{$t('setting.cancel')}}</el-button>
        <el-button type="danger" @click="confirResetPw">{{$t('setting.confirm')}}</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
    getInfo,
    checkGg,
    resetGg,
    resetPw
} from '@/api/setting'

const defaulnewpw = {
    google: '',
    new_password: ''
}

export default {
    data() {
        return {
            info: {},
            dialogVisible: false,
            gg_key: '******************',
            newpw: Object.assign({}, defaulnewpw),
            passwordType: 'password',
            capsTooltip: false
        }
    },
    created() {
        this.getInfo()
    },
    methods: {
        // 获取IP地址列表
        async getInfo(ipname) {
            const res = await getInfo()
            this.info = res.data
        },
        checkCapslock(e) {
            const {
                key
            } = e
            this.capsTooltip = key && key.length === 1 && (key >= 'A' && key <= 'Z')
        },
        showPwd() {
            if (this.passwordType === 'password') {
                this.passwordType = ''
            } else {
                this.passwordType = 'password'
            }
            this.$nextTick(() => {
                this.$refs.password.focus()
            })
        },
        /* 重置谷歌密钥*/
        handleResetGg() {
            this.$prompt(this.$t('method.enterGoogleCode'), this.$t('method.prompt'), {
                confirmButtonText: this.$t('method.confirmReset'),
                cancelButtonText: this.$t('method.cancel'),
                inputPattern: /^[\d]*$/,
                type: 'primary'
            }).then(async(value) => {
                try {
                    await resetGg({
                        'google': value.value
                    })
                } catch (err) {
                    return
                }
                this.$message({
                    type: 'success',
                    message: this.$t('method.resetSuccess')
                })
                this.getInfo()
            }).catch(() => {})
        },
        /* 查看谷歌密钥*/
        handlecheckGg() {
            this.$prompt(this.$t('method.enterGoogleCode'), this.$t('method.prompt'), {
		        confirmButtonText: this.$t('method.confirmCheck'),
		        cancelButtonText: this.$t('method.cancel'),
                inputPattern: /^[\d]*$/,
                type: 'primary'
            }).then(async(value) => {
                try {
                    this.gg_key = (await checkGg({
                        'google': value.value
                    })).data
                } catch (err) {
                    return
                }
                this.$message({
                    type: 'success',
                    message: this.$t('method.checkSuccess')
                })
            }).catch(() => {})
        },
        /* 重置密码*/
        handleResetPw() {
            this.dialogVisible = true
            this.newpw = Object.assign({}, defaulnewpw)
        },
        async confirResetPw() {
            try {
                await resetPw(this.newpw)
            } catch (err) {
                return
            }
            this.$message({
                type: 'success',
                message: this.$t('method.resetSuccess')
            })
            this.dialogVisible = false
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

    .show-pwd {
        position: absolute;
        right: -279%;
        font-size: 16px;
        cursor: pointer;
        user-select: none;
    }
</style>
