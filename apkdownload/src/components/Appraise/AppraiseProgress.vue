<script setup>
import { computed } from "vue";
import stars5 from "@/assets/img/stars-5.png";
const props = defineProps({
  starsNum: {
    type: Number,
    default: 5,
  },
  scoreProgress: {
    type: Number,
    default: 0,
  },
});

const stars = computed(() => {
  if ([1, 2, 3, 4, 5, 0].indexOf(props.starsNum) < 0) return 5;

  switch (props.starsNum) {
    case 0:
      return 100;
    case 1:
      return 80;
    case 2:
      return 60;
    case 3:
      return 40;
    case 4:
      return 20;
    case 5:
      return 0;
    default:
      return 0;
  }
});
</script>

<template>
  <div class="appraise">
    <div class="appraise-img">
      <div :style="`width: ${stars}%`"></div>
      <img :src="stars5" />
    </div>
    <div class="appraise-score-container">
      <div
        class="appraise-score-inner"
        :style="`width: ${scoreProgress}%`"
      ></div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.appraise {
  height: 7px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  .appraise-img {
    width: 46px;
    height: 100%;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 10px;
    img {
      max-width: 100%;
      max-height: 100%;
    }
    > div {
      position: absolute;
      background-color: #fff;
      height: 100%;
      left: 0;
      top: 0;
    }
  }

  .appraise-score-container {
    width: 100%;
    height: 2px;
    background-color: #e9e9ec;
    border-radius: 2px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    .appraise-score-inner {
      background: #4a4a4e;
      height: 90%;
      border-radius: 2px;
    }
  }
}
</style>
