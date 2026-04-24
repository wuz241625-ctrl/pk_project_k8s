import { createRouter, createWebHashHistory } from 'vue-router';


const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      redirect: '/app',
      children: [
        {
          path: '/app',
          component: () => import('@/views/apkm.vue'),
          meta: {
            title: 'app'
          }
        },
      ]
    },
    {
      path: '/404',
      name: '404',
      component: () => import('@/views/error/404.vue'),
      meta: {
        title: '404'
      }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/404'
    },
  ],
});

export default router;
