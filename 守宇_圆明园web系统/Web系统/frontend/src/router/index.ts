import { createRouter, createWebHashHistory } from 'vue-router'
import ExplorePage from '@/pages/ExplorePage.vue'
import ChatPage from '@/pages/ChatPage.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/explore' },
    { path: '/explore', component: ExplorePage, meta: { title: '图谱探索' } },
    { path: '/chat', component: ChatPage, meta: { title: 'AI 问答' } },
    { path: '/chat/:sessionId', component: ChatPage, meta: { title: 'AI 问答' } },
  ],
})

export default router
