<script setup>
import Appdownload from "@/components/Appdownload/index.vue";
import defaultLogo from '@/assets/logo/logo-192x192.png';
import d7payLogo from '@/assets/logo/d7pay-logo-192x192.png';

const appLogo = import.meta.env.VITE_APP_KEY === 'd7pay_merchant'
  ? d7payLogo
  : defaultLogo;
</script>

<template>
  <Appdownload :app-logo="appLogo" />
</template>
