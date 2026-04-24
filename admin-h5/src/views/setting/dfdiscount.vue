<template>
    <div class="app-container">
        <el-form :model="dfdiscountData" label-width="160px" label-position="left">
            <el-row :gutter="20">
                <el-col :span="8">
                    <el-form-item :label="$t('method.orderRange1')" style="width: 100%;">
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemin1" :placeholder="$t('method.enterOrderAmountRange')" /></el-col>
                        <el-col :span="2" style="text-align: center;">~</el-col>
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemax1" :placeholder="$t('method.enterOrderAmountRange')" /></el-col>
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item :label="$t('method.discountAmount')">
                        <el-input v-model.number="dfdiscountData.disprice1" :placeholder="$t('method.enterDiscountAmount')" style="width: 150px" />
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item :label="$t('method.isOpen')">
                        <el-switch v-model="dfdiscountData.isOpen1" :active-value="1" :inactive-value="0" active-color="#13ce66" />
                    </el-form-item>
                </el-col>
            </el-row>
            <el-row :gutter="20">
                <el-col :span="8">
                    <el-form-item label="订单金额范围二" style="width: 100%;">
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemin2" placeholder="请输入订单金额范围" /></el-col><el-col :span="2" style="text-align: center;">~</el-col><el-col :span="11"><el-input v-model.number="dfdiscountData.rangemax2" placeholder="请输入订单金额范围" /></el-col>
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="优惠金额">
                        <el-input v-model.number="dfdiscountData.disprice2" placeholder="请输入优惠金额" style="width: 150px" />
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="是否开启">
                        <el-switch v-model="dfdiscountData.isOpen2" :active-value="1" :inactive-value="0" active-color="#13ce66" />
                    </el-form-item>
                </el-col>
            </el-row>
            <el-row :gutter="20">
                <el-col :span="8">
                    <el-form-item label="订单金额范围三" style="width: 100%;">
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemin3" placeholder="请输入订单金额范围" /></el-col><el-col :span="2" style="text-align: center;">~</el-col><el-col :span="11"><el-input v-model.number="dfdiscountData.rangemax3" placeholder="请输入订单金额范围" /></el-col>
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="优惠金额">
                        <el-input v-model.number="dfdiscountData.disprice3" placeholder="请输入优惠金额" style="width: 150px" />
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="是否开启">
                        <el-switch v-model="dfdiscountData.isOpen3" :active-value="1" :inactive-value="0" active-color="#13ce66" />
                    </el-form-item>
                </el-col>
            </el-row>
            <el-row :gutter="20">
                <el-col :span="8">
                    <el-form-item label="订单金额范围四" style="width: 100%;">
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemin4" placeholder="请输入订单金额范围" /></el-col><el-col :span="2" style="text-align: center;">~</el-col><el-col :span="11"><el-input v-model.number="dfdiscountData.rangemax4" placeholder="请输入订单金额范围" /></el-col>
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="优惠金额">
                        <el-input v-model.number="dfdiscountData.disprice4" placeholder="请输入优惠金额" style="width: 150px" />
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="是否开启">
                        <el-switch v-model="dfdiscountData.isOpen4" :active-value="1" :inactive-value="0" active-color="#13ce66" />
                    </el-form-item>
                </el-col>
            </el-row>
            <el-row :gutter="20">
                <el-col :span="8">
                    <el-form-item label="订单金额范围五" style="width: 100%;">
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemin5" placeholder="请输入订单金额范围" /></el-col><el-col :span="2" style="text-align: center;">~</el-col><el-col :span="11"><el-input v-model.number="dfdiscountData.rangemax5" placeholder="请输入订单金额范围" /></el-col>
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="优惠金额">
                        <el-input v-model.number="dfdiscountData.disprice5" placeholder="请输入优惠金额" style="width: 150px" />
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="是否开启">
                        <el-switch v-model="dfdiscountData.isOpen5" :active-value="1" :inactive-value="0" active-color="#13ce66" />
                    </el-form-item>
                </el-col>
            </el-row>
            <el-row :gutter="20">
                <el-col :span="8">
                    <el-form-item label="订单金额范围六" style="width: 100%;">
                        <el-col :span="11"><el-input v-model.number="dfdiscountData.rangemin6" placeholder="请输入订单金额范围" /></el-col><el-col :span="2" style="text-align: center;">~</el-col><el-col :span="11"><el-input v-model.number="dfdiscountData.rangemax6" placeholder="请输入订单金额范围" /></el-col>
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="优惠金额">
                        <el-input v-model.number="dfdiscountData.disprice6" placeholder="请输入优惠金额" style="width: 150px" />
                    </el-form-item>
                </el-col>
                <el-col :span="8">
                    <el-form-item label="是否开启">
                        <el-switch v-model="dfdiscountData.isOpen6" :active-value="1" :inactive-value="0" active-color="#13ce66" />
                    </el-form-item>
                </el-col>
            </el-row>
            <el-form-item :label="$t('method.googleCode')" style="width: 300px;">
                <el-input v-model="dfdiscountData.google" :placeholder="$t('method.enterGoogleCode')" />
            </el-form-item>
            <el-button type="danger" class="confButton" @click="confirmRole">{{ $t('method.saveButton') }}</el-button>
        </el-form>
    </div>
</template>

<script>
import {getDfdiscount, getWeight, updateDfdiscount, updateWeight} from '@/api/setting'

export default {
    data() {
        return {
            dfdiscountData: {},
            weightData: {}
        }
    },
    created() {
        this.getData()
        this.getWeight()
    },
    methods: {
    // 获取设置
    async getData() {
            const res = await getDfdiscount()
            this.dfdiscountData = res.data
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
    /* 保存*/
    async confirmRole() {
        if (isNaN(this.dfdiscountData.google) || this.dfdiscountData.google.length < 6) {
            this.$message({
                type: 'warning',
                message: this.$t('method.dfdiscount.googleCodeLength')
            });
            return;
        }

        // 获取所有的isOpen
        this.dfdiscountData.isOpen1 = this.dfdiscountData.isOpen1 ? 1 : 0;
        this.dfdiscountData.isOpen2 = this.dfdiscountData.isOpen2 ? 1 : 0;
        this.dfdiscountData.isOpen3 = this.dfdiscountData.isOpen3 ? 1 : 0;
        this.dfdiscountData.isOpen4 = this.dfdiscountData.isOpen4 ? 1 : 0;
        this.dfdiscountData.isOpen5 = this.dfdiscountData.isOpen5 ? 1 : 0;
        this.dfdiscountData.isOpen6 = this.dfdiscountData.isOpen6 ? 1 : 0;

        // 如果开启 则订单范围和优惠金额不能为空
        if (this.dfdiscountData.isOpen1 == 1) {
                if (isNaN(this.dfdiscountData.rangemin1) || isNaN(this.dfdiscountData.rangemax1) || isNaN(this.dfdiscountData.disprice1) || this.dfdiscountData.rangemin1 == '' || this.dfdiscountData.rangemax1 == '' || this.dfdiscountData.disprice1 == '') {
                    var message1 = '订单范围和优惠金额不能为空（订单金额范围一）'
                    this.$message({
                        type: 'warning',
                        message: message1
                    })
                    return
                }
            }
            if (this.dfdiscountData.isOpen2 == 1) {
                if (isNaN(this.dfdiscountData.rangemin2) || isNaN(this.dfdiscountData.rangemax2) || isNaN(this.dfdiscountData.disprice2) || this.dfdiscountData.rangemin2 == '' || this.dfdiscountData.rangemax2 == '' || this.dfdiscountData.disprice2 == '') {
                    var message2 = '订单范围和优惠金额不能为空（订单金额范围二）'
                    this.$message({
                        type: 'warning',
                        message: message2
                    })
                    return
                }
            }
            if (this.dfdiscountData.isOpen3 == 1) {
                if (isNaN(this.dfdiscountData.rangemin3) || isNaN(this.dfdiscountData.rangemax3) || isNaN(this.dfdiscountData.disprice3) || this.dfdiscountData.rangemin3 == '' || this.dfdiscountData.rangemax3 == '' || this.dfdiscountData.disprice3 == '') {
                    var message3 = '订单范围和优惠金额不能为空（订单金额范围三）'
                    this.$message({
                        type: 'warning',
                        message: message3
                    })
                    return
                }
            }
            if (this.dfdiscountData.isOpen4 == 1) {
                if (isNaN(this.dfdiscountData.rangemin4) || isNaN(this.dfdiscountData.rangemax4) || isNaN(this.dfdiscountData.disprice4) || this.dfdiscountData.rangemin4 == '' || this.dfdiscountData.rangemax4 == '' || this.dfdiscountData.disprice4 == '') {
                    var message4 = '订单范围和优惠金额不能为空（订单金额范围四）'
                    this.$message({
                        type: 'warning',
                        message: message4
                    })
                    return
                }
            }
            if (this.dfdiscountData.isOpen5 == 1) {
                if (isNaN(this.dfdiscountData.rangemin5) || isNaN(this.dfdiscountData.rangemax5) || isNaN(this.dfdiscountData.disprice5) || this.dfdiscountData.rangemin5 == '' || this.dfdiscountData.rangemax5 == '' || this.dfdiscountData.disprice5 == '') {
                    var message5 = '订单范围和优惠金额不能为空（订单金额范围五）'
                    this.$message({
                        type: 'warning',
                        message: message5
                    })
                    return
                }
            }
            if (this.dfdiscountData.isOpen6 == 1) {
                if (isNaN(this.dfdiscountData.rangemin6) || isNaN(this.dfdiscountData.rangemax6) || isNaN(this.dfdiscountData.disprice6) || this.dfdiscountData.rangemin6 == '' || this.dfdiscountData.rangemax6 == '' || this.dfdiscountData.disprice6 == '') {
                    var message6 = '订单范围和优惠金额不能为空（订单金额范围六）'
                    this.$message({
                        type: 'warning',
                        message: message6
                    })
                    return
                }
            }
            if (this.dfdiscountData.rangemin1 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemin1)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围一）'
                })
                return
            }
            if (this.dfdiscountData.rangemax1 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemax1)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围一）'
                })
                return
            }
            if (this.dfdiscountData.disprice1 && !/^[1-9]\d*$/.test(this.dfdiscountData.disprice1)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围一）'
                })
                return
            }
            if (this.dfdiscountData.rangemin2 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemin2)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围二）'
                })
                return
            }
            if (this.dfdiscountData.rangemax2 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemax2)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围二）'
                })
                return
            }
            if (this.dfdiscountData.disprice2 && !/^[1-9]\d*$/.test(this.dfdiscountData.disprice2)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围二）'
                })
                return
            }
            if (this.dfdiscountData.rangemin3 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemin3)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围三）'
                })
                return
            }
            if (this.dfdiscountData.rangemax3 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemax3)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围三）'
                })
                return
            }
            if (this.dfdiscountData.disprice3 && !/^[1-9]\d*$/.test(this.dfdiscountData.disprice3)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围三）'
                })
                return
            }
            if (this.dfdiscountData.rangemin4 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemin4)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围四）'
                })
                return
            }
            if (this.dfdiscountData.rangemax4 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemax4)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围四）'
                })
                return
            }
            if (this.dfdiscountData.disprice4 && !/^[1-9]\d*$/.test(this.dfdiscountData.disprice4)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围四）'
                })
                return
            }
            if (this.dfdiscountData.rangemin5 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemin5)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围五）'
                })
                return
            }
            if (this.dfdiscountData.rangemax5 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemax5)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围五）'
                })
                return
            }
            if (this.dfdiscountData.disprice5 && !/^[1-9]\d*$/.test(this.dfdiscountData.disprice5)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围五）'
                })
                return
            }
            if (this.dfdiscountData.rangemin6 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemin6)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围六）'
                })
                return
            }
            if (this.dfdiscountData.rangemax6 && !/^[1-9]\d*$/.test(this.dfdiscountData.rangemax6)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围六）'
                })
                return
            }
            if (this.dfdiscountData.disprice6 && !/^[1-9]\d*$/.test(this.dfdiscountData.disprice6)) {
                this.$message({
                    type: 'warning',
                    message: '请输入正整数（订单金额范围六）'
                })
                return
            }

            const ranges = []
            // 填写了才追加进去
            if (this.dfdiscountData.isOpen1 == 1) {
                ranges.push([this.dfdiscountData.rangemin1, this.dfdiscountData.rangemax1])
            }
            if (this.dfdiscountData.isOpen2 == 1) {
                ranges.push([this.dfdiscountData.rangemin2, this.dfdiscountData.rangemax2])
            }
            if (this.dfdiscountData.isOpen3 == 1) {
                ranges.push([this.dfdiscountData.rangemin3, this.dfdiscountData.rangemax3])
            }
            if (this.dfdiscountData.isOpen4 == 1) {
                ranges.push([this.dfdiscountData.rangemin4, this.dfdiscountData.rangemax4])
            }
            if (this.dfdiscountData.isOpen5 == 1) {
                ranges.push([this.dfdiscountData.rangemin5, this.dfdiscountData.rangemax5])
            }
            if (this.dfdiscountData.isOpen6 == 1) {
                ranges.push([this.dfdiscountData.rangemin6, this.dfdiscountData.rangemax6])
            }
            for (let i = 0; i < ranges.length; i++) {
                for (let j = i + 1; j < ranges.length; j++) {
                    if (ranges[i][0] <= ranges[j][1] && ranges[j][0] <= ranges[i][1]) {
                        this.$message({
                            type: 'warning',
                            message: '订单金额范围不允许嵌套,请检查'
                        })
                        return
                    }
                }
            }
            // 如果非isNaN，则最小金额不能大于最大金额
            if (this.dfdiscountData.rangemin1 > this.dfdiscountData.rangemax1) {
                this.$message({
                    type: 'warning',
                    message: '最小金额不能大于最大金额（订单金额范围一）'
                })
                return
            }
            if (this.dfdiscountData.rangemin2 > this.dfdiscountData.rangemax2) {
                this.$message({
                    type: 'warning',
                    message: '最小金额不能大于最大金额（订单金额范围二）'
                })
                return
            }
            if (this.dfdiscountData.rangemin3 > this.dfdiscountData.rangemax3) {
                this.$message({
                    type: 'warning',
                    message: '最小金额不能大于最大金额（订单金额范围三）'
                })
                return
            }
            if (this.dfdiscountData.rangemin4 > this.dfdiscountData.rangemax4) {
                this.$message({
                    type: 'warning',
                    message: '最小金额不能大于最大金额（订单金额范围四）'
                })
                return
            }
            if (this.dfdiscountData.rangemin5 > this.dfdiscountData.rangemax5) {
                this.$message({
                    type: 'warning',
                    message: '最小金额不能大于最大金额（订单金额范围五）'
                })
                return
            }
            if (this.dfdiscountData.rangemin6 > this.dfdiscountData.rangemax6) {
                console.log(this.dfdiscountData.rangemin6, this.dfdiscountData.rangemax6)
                this.$message({
                    type: 'warning',
                    message: '最小金额不能大于最大金额（订单金额范围六）'
                })
                return
            }
            // 订单金额范围不允许嵌套 判断所有提交的订单金额范围是否有交集
            // 1.判断是否有交集
        try {
            await updateDfdiscount(this.dfdiscountData);
        } catch (err) {
            return;
        }
        this.$notify({
            title: this.$t('dfdiscount.saveSuccess'),
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
            this.$confirm(this.$t('dfdiscount.positiveIntegerPrompt'), this.$t('dfdiscount.prompt'), {
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

        // 更多处理逻辑...
    },
    // 保存权重
    async confirmWeight() {
        if (isNaN(this.weightData.google) || this.weightData.google.length < 6) {
            this.$message({
                type: 'warning',
                message: this.$t('dfdiscount.googleCodeLength')
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
            title: this.$t('dfdiscount.saveSuccess'),
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
