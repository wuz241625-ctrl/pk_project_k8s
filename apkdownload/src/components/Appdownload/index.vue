<script setup>
import { ref, onMounted } from "vue";
import { AppraiseProgress, FractionalAndAge } from "@/components/Appraise";
const props = defineProps({
  appLogo: {
    type: String,
    default: "",
  },
});
const baseUrl = window.location.origin;
const appPath = ref("");
const filename = ref("");
const appKey = import.meta.env.VITE_APP_KEY || "ashrafi_merchant";
const legacyAppKey = import.meta.env.VITE_APP_FALLBACK_KEY || "lakshmi";

const information = ref({
  name: "Ashrafi Merchant",
  developer: "",
  compatibility: "",
  language: "",
  size: "",
  updateTime: "",
  introduction: "",
  version: "",
});

onMounted(async () => {
  const res = await fetch(
    `${baseUrl}/files/android/appInfo.json?v=${new Date().getTime()}`
  );
  const data = await res.json();
  const appInfo = data[appKey] || data[legacyAppKey] || {};
  appPath.value = appInfo.path ? `${baseUrl}${appInfo.path}` : "";
  filename.value = appInfo.filename || "AshrafiMerchant.apk";
  information.value = {
    name: appInfo.name || "Ashrafi Merchant",
    developer: appInfo.developer || null,
    compatibility: appInfo.compatibility || null,
    language: appInfo.language || null,
    size: appInfo.size || null,
    updateTime: appInfo.updateTime || null,
    introduction: appInfo.introduction || "",
    version: appInfo.version || "-",
  };
  document.title = information.value.name;
});
</script>

<template>
  <div class="app-download">
    <div class="app-info">
      <div class="info-head">
        <div class="app-logo">
          <img :src="appLogo" />
        </div>
        <div class="down-btn flexc">
          <div class="app-name">{{ information.name }}</div>
          <a
            v-if="appPath"
            class="download-btn"
            :href="appPath"
            :download="filename"
            >Android Install</a
          >
          <span v-else class="download-btn download-btn-disabled">APK Pending</span>
        </div>
      </div>
      <div class="b-b">
        <FractionalAndAge
          style="margin-bottom: 20px"
          :stars-num="5"
          score="4.9"
          :age="4"
          total="9999"
        />
      </div>
      <div class="app-score b-b">
        <h2 style="text-align: center">Ratings and comments</h2>
        <div class="flexc score-detail">
          <div style="width: 90px; margin-right: 10px">
            <div style="font-size: 56px; font-weight: 600">4.9</div>
            <div style="color: #8e8e8e; font-weight: 300; font-size: 14px">
              The full score is 5
            </div>
          </div>
          <div class="app-score-right">
            <AppraiseProgress style="margin-bottom: 5px" :score-progress="80" />
            <AppraiseProgress style="margin-bottom: 5px" :score-progress="20" />
            <AppraiseProgress style="margin-bottom: 5px" :stars-num="4" />
            <AppraiseProgress style="margin-bottom: 5px" :stars-num="3" />
            <AppraiseProgress style="margin-bottom: 5px" :stars-num="2" />
          </div>
        </div>
      </div>
      <div class="app-details-info b-b" style="margin-bottom: 10px">
        <h2 style="text-align: center">Introduction</h2>
        <p style="color: #8e8e8e; font-size: 14px; line-height: 20px">
          {{ information.introduction }}
        </p>
      </div>

      <div class="new-fun b-b">
        <h2 style="text-align: center">New Function</h2>
        <p style="text-align: center; font-weight: 300">
          Version v{{ information.version }}
        </p>
      </div>

      <div class="information">
        <h2 style="text-align: center; margin-bottom: 10px">Information</h2>
        <div class="b-b infomation-item" v-if="information.developer">
          <div>Developer</div>
          <div>{{ information.developer }}</div>
        </div>
        <div class="b-b infomation-item" v-if="information.compatibility">
          <div>Compatibility</div>
          <div>{{ information.compatibility }}</div>
        </div>
        <div class="b-b infomation-item" v-if="information.language">
          <div>Language</div>
          <div>{{ information.language }}</div>
        </div>
        <div class="b-b infomation-item" v-if="information.size">
          <div>Size</div>
          <div>{{ information.size }}</div>
        </div>
        <div class="b-b infomation-item" v-if="information.updateTime">
          <div>Update Time</div>
          <div>{{ information.updateTime }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.flexc {
  display: flex;
  align-items: center;
  justify-content: center;
}
.b-b {
  border-bottom: 1px solid #e8e8e8;
}
.app-download {
  width: 100%;
  box-sizing: border-box;
  padding: 20px;
  font-size: 14px;
  color: #333;

  .app-info {
    .info-head {
      padding: 0 20px;
      display: flex;
      .app-logo {
        width: 104px;
        img {
          width: 100%;
        }
      }
      .down-btn {
        width: calc(100vw - 104px);
        flex-direction: column;

        .app-name {
          font-weight: 500;
          font-size: 18px;
          margin-bottom: 25px;
        }

        .download-btn {
          display: inline-block;
          background-color: #1088df;
          padding: 4px 12px;
          border-radius: 16px;
          color: #fff;
          font-size: 12px;
          font-weight: 300;
          cursor: pointer;
          text-decoration: none;
        }
        .download-btn-disabled {
          background-color: #8e8e8e;
          cursor: not-allowed;
        }
      }
      margin-bottom: 30px;
    }

    .app-score {
      padding-bottom: 20px;
      .score-detail {
        justify-content: space-between;
      }
      .app-score-right {
        width: calc(100vw - 110px);
        padding: 20px;
      }
    }

    .new-fun {
      padding-bottom: 10px;
    }

    .infomation-item {
      padding: 16px 5px;
      @extend .flexc;
      justify-content: space-between;
      font-size: 12px;
    }
  }
}
</style>
