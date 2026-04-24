<template>
  <div class="app-container">
    <el-form :model="otherData" label-width="150px" label-position="left">
      <el-form-item :label="$t('qtsz.form.dfRate')" style="width: 300px;">
        <el-input v-model="otherData.rate_df" :placeholder="$t('qtsz.form.placeholder')" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.bulletin')">
        <el-input v-model="otherData.bulletin" :placeholder="$t('qtsz.form.placeholder')" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.customerService')">
        <el-input v-model="otherData.telegram" :placeholder="$t('qtsz.form.customerServicePlaceholder')" />
      </el-form-item>
      
      <el-form-item label="假码接单">
        <el-input v-model="otherData.payment_ids" placeholder="请输入假码接单,号隔开" />
      </el-form-item>
      
      <el-form-item label="自动解封付款特定金额">
        <el-input v-model="otherData.unlock_amount" placeholder="请输入自动解封付款特定金额,号隔开" />
      </el-form-item>

      <el-form-item :label="$t('qtsz.form.publicAccountSetting')">
        <el-input v-model="otherData.gonghu_ds_payment" :placeholder="$t('qtsz.form.publicAccountSettingPlaceholder')" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.dfSwitch')">
        <el-switch v-model="otherData.status_df" :active-value="1" :inactive-value="0" active-color="#13ce66" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.dfExpiredSwitch')">
        <el-switch v-model="otherData.expired_status_df" :active-value="1" :inactive-value="0" active-color="#13ce66" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.usdtRate')">
        <el-input v-model="otherData.usdt_exchange_rate" :placeholder="$t('qtsz.form.placeholder')" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.usdtSwitch')">
        <el-switch v-model="otherData.usdt_exchange_status" :active-value="1" :inactive-value="0" active-color="#13ce66" />
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.usdtBonusRate')">
        <el-input v-model="otherData.usdt_exchange_bonus_rate" :placeholder="$t('qtsz.form.placeholder')" />
      </el-form-item>
      <el-form-item label="usdt金额限制">
        <el-input v-model="otherData.usdt_amount_limit" :placeholder="$t('qtsz.form.placeholder')"/>
      </el-form-item>

      <el-form-item label="商户编号">
        <el-input v-model="otherData.merchant_ids" :autosize="{ minRows: 8, maxRows: 20}" type="textarea" placeholder="请输入,号隔开" />
     </el-form-item>

      <el-form-item :label="$t('qtsz.form.googleCode')" style="width: 300px;">
        <el-input v-model="otherData.google" :placeholder="$t('qtsz.form.placeholder')" />
      </el-form-item>
      <el-button type="danger" class="confButton" @click="confirmRole">{{ $t('qtsz.form.save') }}</el-button>
    </el-form>
    <el-divider></el-divider>
    <el-row :gutter="20" style="text-align: center;height: 30px;font-size:20px">{{ $t('qtsz.form.setWeight') }}</el-row>
    <el-row :gutter="20" style="text-align: center;height: 30px;font-size:20px">{{ $t('qtsz.form.weightDescription') }}</el-row>

    <el-form label-position="left">
      <el-form-item v-for="(item, index) in weightData" :key="index">
        <label v-if="item.id == 21" v-html="$t('qtsz.form.newCode') + ' (' + item.payment_numbers + ' ' + $t('qtsz.form.unit') + ')'"></label>
        <label v-if="item.id == 22" v-html="$t('qtsz.form.priority') + ' (' + item.payment_numbers + ' ' + $t('qtsz.form.unit') + ')'"></label>
        <label v-if="item.id != 21 && item.id != 22" v-html="$t('qtsz.form.weightGreater') + item.value + ' % (' + item.payment_numbers + ' ' + $t('qtsz.form.unit') + ')'"></label>
        <el-input v-model="item.weight" :placeholder="$t('qtsz.form.setWeightPlaceholder')" style="width: 100px;margin-left: 30px;" @input="() => handleInput(item, weightData)" />
        <label v-if="item.payment_numbers > 0" style="color:red;font-weight:bolder;font-size:30px"><i class="el-icon-user-solid"></i></label>
        <label v-if="item.payment_numbers > 0" v-html="'(' + item.all_code_probability + '%' + '    '" style="color:red;font-weight:bolder;font-size:30px"></label>
        <label v-if="item.payment_numbers > 0" v-html="item.one_code_probability + '%)'" style="color:red;font-weight:bolder;font-size:30px"></label>
      </el-form-item>
      <el-form-item :label="$t('qtsz.form.googleCode')" label-width="100px" style="width: 300px;">
        <el-input v-model="weightData.google" :placeholder="$t('qtsz.form.placeholder')" />
      </el-form-item>
      <el-button type="danger" class="confButton" @click="confirmWeight">{{ $t('qtsz.form.save') }}</el-button>
    </el-form>
  </div>
</template>

<script>
    import {
        getOther,
        updateOther,
        getWeight,
        updateWeight,
    } from '@/api/setting'
    export default {
        data() {
            return {
                otherData: {},
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
                const res = await getOther()
                this.otherData = res.data
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
        if (isNaN(this.otherData.google) || this.otherData.google.length < 6) {
            this.$message({
                type: 'warning',
                message: this.$t('method.save.googleCodeWarning')
            });
            return;
        }
        try {
            await updateOther(this.otherData);
        } catch (err) {
            return;
        }
        this.$notify({
            title: this.$t('method.save.successTitle'),
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
            this.$confirm(this.$t('method.handleInput.invalidWeightMessage'), this.$t('method.handleInput.promptTitle'), {
                type: 'warning',
                confirmButtonText: this.$t('dfdiscount.confirm'),
                cancelButtonText: this.$t('dfdiscount.cancel'),
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
            this.$message({
                type: 'warning',
                message: this.$t('method.weight.save.googleCodeWarning')
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
            title: this.$t('method.weight.save.successTitle'),
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
