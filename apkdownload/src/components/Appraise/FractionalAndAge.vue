<script setup>
import { computed } from "vue";
import stars5 from "@/assets/img/stars-5.png";
const props = defineProps({
  score: {
    type: [Number, String],
    default: 0,
  },
  starsNum: {
    type: Number,
    default: 0,
  },
  age: {
    type: Number,
    default: 4,
  },
  total: {
    type: [Number, String],
    default: "0",
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
  <div class="fractional-and-age">
    <div class="fractional-and-age_left">
      <div class="fractional-and-age_left-score">
        <div class="current-score">{{ score }}</div>
        <div class="fractional-and-age_img-container">
          <div :style="`width: ${stars}%`"></div>
          <img :src="stars5" />
        </div>
      </div>
      <div style="font-size: 12px;color: #e8e8e8;">{{ total }}+Score</div>
    </div>
    <div class="fractional-and-right">
      <div style="margin-bottom: 10px;text-align: center;">{{ age }}+</div>
      <div style="font-size: 12px;color: #e8e8e8;text-align: center;">Age</div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.fractional-and-age {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  &_left {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;

    &-score {
      display: flex;
      align-items: center;
      margin-bottom: 10px;

      .current-score {
        font-size: 16px;
        font-weight: 600;
        margin-right: 10px;
      }

      .fractional-and-age_img-container {
        width: 80px;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        > div {
          position: absolute;
          right: 0;
          top: 0;
          height: 100%;
          background-color: #fff;
        }
        img {
          max-width: 100%;
        }
      }
    }
  }
}
</style>
