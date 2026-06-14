/**
 * Pinia：全局 AI 上下文篮（跨页共享）
 *
 * 严格按 CLAUDE.md 第 17 章设计。
 */
import { defineStore } from 'pinia'

export interface ContextItem {
  id: string
  idKind: 'event' | 'entity'
  name: string
  label: string
  type_cn: string
  color: string
  addedFrom: 'explore' | 'chat'
  note?: string
}

const MAX_CONTEXT = 12
const STORAGE_KEY = 'ym_context_items'
let _toastTimer: any = null

// 简单非阻塞 toast（不弹窗打断用户）
function showToast(msg: string) {
  if (_toastTimer) clearTimeout(_toastTimer)
  const el = document.createElement('div')
  el.className = 'context-toast'
  el.textContent = msg
  document.body.appendChild(el)
  requestAnimationFrame(() => el.classList.add('show'))
  _toastTimer = setTimeout(() => {
    el.classList.remove('show')
    setTimeout(() => el.remove(), 300)
  }, 2500)
}

function loadFromStorage(): ContextItem[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveToStorage(items: ContextItem[]) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items))
}

export const useContextStore = defineStore('context', {
  state: () => ({
    items: loadFromStorage() as ContextItem[],
    open: false,
  }),

  getters: {
    pinnedIds: (state) => state.items.map((i) => i.id),
    count: (state) => state.items.length,
  },

  actions: {
    addItem(item: ContextItem) {
      // 去重
      if (this.items.find((i) => i.id === item.id)) return
      if (this.items.length >= MAX_CONTEXT) {
        showToast(`上下文篮已满（最多 ${MAX_CONTEXT} 个），请先移除部分节点。`)
        return
      }
      this.items.push(item)
      saveToStorage(this.items)
    },

    removeItem(id: string) {
      this.items = this.items.filter((i) => i.id !== id)
      saveToStorage(this.items)
    },

    clear() {
      this.items = []
      saveToStorage(this.items)
    },

    toggle() {
      this.open = !this.open
    },

    setNote(id: string, text: string) {
      const item = this.items.find((i) => i.id === id)
      if (item) {
        item.note = text
        saveToStorage(this.items)
      }
    },
  },
})
