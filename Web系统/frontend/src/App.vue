<script setup lang="ts">
import TopNav from '@/components/TopNav.vue'
import ContextTray from '@/components/ContextTray.vue'
import { useContextStore } from '@/stores/context'

const context = useContextStore()
</script>

<template>
  <div class="app-shell">
    <TopNav />
    <main class="app-main">
      <router-view />
    </main>

    <!-- 全局上下文篮浮层 -->
    <Transition name="tray-slide">
      <ContextTray v-if="context.open" />
    </Transition>

    <!-- 键盘快捷键提示 -->
    <Teleport to="body">
      <div v-if="context.open" class="overlay" @click="context.toggle()" />
    </Teleport>
  </div>
</template>

<style>
/* ── 全局 Reset & 字体 ── */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  font-family: "PingFang SC", "Microsoft YaHei", "Source Han Sans SC", sans-serif;
  font-size: 14px;
  color: #2B2A28;
  background: #FAF8F3;
  -webkit-font-smoothing: antialiased;
}

#app {
  height: 100%;
}

.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-main {
  flex: 1;
  overflow: hidden;
  position: relative;
}

/* ── 全局 CSS 变量 ── */
:root {
  --bg-canvas: #FAF8F3;
  --bg-panel: #FFFFFF;
  --bg-subtle: #F2EFE9;
  --border: #E3DED4;
  --text-primary: #2B2A28;
  --text-secondary: #6B665E;
  --text-muted: #9A938A;
  --accent: #B5503C;
  --radius: 6px;
  --radius-sm: 4px;
  --shadow-sm: 0 1px 3px rgba(40, 36, 30, 0.08);
}

/* ── 过渡动效 ── */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s ease-out;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.tray-slide-enter-active, .tray-slide-leave-active {
  transition: transform 0.2s ease-out, opacity 0.2s ease-out;
}
.tray-slide-enter-from, .tray-slide-leave-to {
  transform: translateY(-8px);
  opacity: 0;
}

.overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: transparent;
}

/* ── 滚动条 ── */
::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #D5CFC4;
  border-radius: 3px;
}

/* ── Toast 提示 ── */
.context-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(20px);
  background: var(--text-primary);
  color: #fff;
  padding: 10px 20px;
  border-radius: var(--radius);
  font-size: 13px;
  font-family: inherit;
  z-index: 9999;
  opacity: 0;
  transition: opacity 0.25s, transform 0.25s;
  pointer-events: none;
}
.context-toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
</style>
