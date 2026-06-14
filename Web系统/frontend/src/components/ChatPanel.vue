<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import GraphRAGSteps from './GraphRAGSteps.vue'
import type { GraphRAGStep } from '@/stores/chat'

const props = defineProps<{
  messages: any[]
  streaming: boolean
  pinnedCount: number
  error: string | null
  deepMode: boolean
  ragSteps: GraphRAGStep[]
  ragActive: boolean
}>()

const emit = defineEmits<{
  'send': [question: string]
  'stop': []
  'citation-click': [nodeId: string]
  'toggle-deep': [value: boolean]
}>()

const inputText = ref('')
const messagesEl = ref<HTMLDivElement>()
const exampleQuestions = [
  '雍正二年圆明园营造涉及哪些机构？',
  '导致圆明园失火的前因后果？',
  '允禄在圆明园采办木植事件中的角色？',
]

function send() {
  const q = inputText.value.trim()
  if (!q || props.streaming) return
  emit('send', q)
  inputText.value = ''
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

// 自动滚动
watch(() => props.messages.length, () => {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
})

// Fix4: 将 AI 文本中的 【id】替换为可点击元素 + 处理 citation markers
function renderContent(text: string, citations: any[]): string {
  if (!text) return ''

  // 构建 citation map: id → marker (①, ②, ...)
  // 后端 parse_citations 发送 { id: "evt_xxx", marker: "①" }
  const citeMap: Record<string, string> = {}
  if (citations?.length) {
    citations.forEach((c) => {
      if (c.id && c.marker) citeMap[c.id] = c.marker
    })
  }

  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n\n/g, '<br><br>')

  // 将换行的 - 开头转为列表项
  html = html.replace(/\n- (.+)/g, '\n<li>$1</li>')

  // Fix4: 替换 【id】为可点击引用角标
  html = html.replace(/【(evt_[^】]+|ent_[^】]+)】/g, (_, id: string) => {
    const marker = citeMap[id] || id
    return `<span class="cite-inline" data-node-id="${id}" title="${id}">【${marker}】</span>`
  })

  return html
}

// 处理引用点击（事件委托）
function onMsgClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains('cite-inline')) {
    const nodeId = target.dataset.nodeId
    if (nodeId) emit('citation-click', nodeId)
  }
}
</script>

<template>
  <div class="chat-panel">
    <!-- 消息列表 -->
    <div ref="messagesEl" class="messages-area">
      <!-- 空状态 -->
      <div v-if="messages.length === 0" class="chat-empty">
        <p class="empty-title">圆明园历史档案 AI 研究助理</p>
        <p class="empty-desc">基于知识图谱的史料检索与问答。您可以：</p>
        <div class="example-grid">
          <button
            v-for="q in exampleQuestions"
            :key="q"
            class="example-btn"
            @click="emit('send', q)"
          >
            {{ q }}
          </button>
        </div>
      </div>

      <!-- 消息 -->
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="msg-row"
        :class="msg.role"
      >
        <div class="msg-avatar">
          {{ msg.role === 'user' ? '👤' : '🤖' }}
        </div>
        <div class="msg-bubble">
          <!-- GraphRAG 步骤展示（仅深度检索时） -->
          <GraphRAGSteps
            v-if="ragActive && i === messages.length - 1 && msg.role === 'assistant'"
            :steps="ragSteps"
          />

          <!-- 检索提示 -->
          <div v-if="msg.retrievalGraph && !ragActive" class="retrieval-note">
            已检索 {{ msg.retrievalGraph.nodes?.length || 0 }} 条相关资料
          </div>

          <!-- Fix4: 内容区带可点击引用，事件委托处理 -->
          <div
            v-if="msg.content"
            class="msg-content"
            v-html="renderContent(msg.content, msg.citations)"
            @click="onMsgClick"
          ></div>

          <!-- 可折叠引用列表 -->
          <details v-if="msg.citations?.length" class="ref-details">
            <summary>📎 引用资料 ({{ msg.citations.length }})</summary>
            <div
              v-for="c in msg.citations"
              :key="'r-' + c.id"
              class="ref-item"
              @click="emit('citation-click', c.id)"
            >
              <span class="ref-marker">{{ c.marker }}</span>
              <span class="ref-id">{{ c.id }}</span>
            </div>
          </details>
        </div>
      </div>

      <!-- 错误提示 -->
      <div v-if="error" class="error-bar">
        {{ error }}
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <p v-if="pinnedCount > 0" class="pinned-hint">
        将参考 {{ pinnedCount }} 个已引入节点
      </p>
      <div class="mode-row">
        <label class="deep-toggle" :class="{ active: props.deepMode }">
          <input
            type="checkbox"
            :checked="props.deepMode"
            :disabled="streaming"
            @change="emit('toggle-deep', ($event.target as HTMLInputElement).checked)"
          />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
          <span class="toggle-label">深度检索</span>
        </label>
        <span v-if="props.deepMode" class="deep-hint">GraphRAG · 多轮推理</span>
      </div>
      <div class="input-row">
        <textarea
          v-model="inputText"
          class="chat-input"
          rows="2"
          placeholder="输入问题… (Enter 发送，Shift+Enter 换行)"
          :disabled="streaming"
          @keydown="handleKeydown"
        ></textarea>
        <button
          v-if="!streaming"
          class="btn-send"
          @click="send"
          :disabled="!inputText.trim()"
        >
          发送
        </button>
        <button
          v-else
          class="btn-stop"
          @click="emit('stop')"
        >
          停止
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-panel);
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.chat-empty {
  text-align: center;
  padding-top: 60px;
}
.empty-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.empty-desc { font-size: 14px; color: var(--text-secondary); margin-bottom: 24px; }
.example-grid { display: flex; flex-direction: column; gap: 8px; max-width: 420px; margin: 0 auto; }
.example-btn {
  padding: 10px 16px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg-canvas); font-size: 13px; font-family: inherit;
  color: var(--text-secondary); cursor: pointer; text-align: left; transition: all 0.15s;
}
.example-btn:hover { border-color: var(--accent); color: var(--accent); background: #B5503C08; }

.msg-row { display: flex; gap: 10px; margin-bottom: 20px; }
.msg-row.user { flex-direction: row-reverse; }
.msg-avatar { font-size: 22px; width: 32px; flex-shrink: 0; text-align: center; }
.msg-bubble {
  max-width: 75%; padding: 12px 16px; border-radius: var(--radius);
  font-size: 14px; line-height: 1.7;
}
.msg-row.user .msg-bubble { background: var(--bg-subtle); color: var(--text-primary); }
.msg-row.assistant .msg-bubble { background: var(--bg-canvas); border: 1px solid var(--border); color: var(--text-primary); }

.retrieval-note {
  font-size: 12px; color: var(--accent); margin-bottom: 8px;
  padding-bottom: 6px; border-bottom: 1px solid var(--border);
}

.msg-content { word-break: break-word; }

/* Fix4: 可点击引用角标 */
:deep(.cite-inline) {
  display: inline;
  color: var(--accent);
  cursor: pointer;
  font-weight: 500;
  font-size: 0.9em;
  padding: 0 1px;
  transition: background 0.15s;
  border-radius: 2px;
}
:deep(.cite-inline:hover) {
  background: #B5503C1A;
}

.ref-details { margin-top: 10px; font-size: 12px; }
.ref-details summary { color: var(--text-secondary); cursor: pointer; }
.ref-item {
  display: flex; gap: 6px; padding: 3px 6px; margin-top: 2px;
  cursor: pointer; border-radius: 2px; transition: background 0.1s;
}
.ref-item:hover { background: var(--bg-subtle); }
.ref-marker { color: var(--accent); font-weight: 500; }
.ref-id { color: var(--text-muted); font-family: monospace; }

.error-bar {
  padding: 10px 16px; background: #FDF2F2; color: #B5503C;
  font-size: 13px; border-radius: var(--radius-sm); margin-top: 8px;
}

.input-area { padding: 12px 20px; border-top: 1px solid var(--border); background: var(--bg-panel); }
.pinned-hint { font-size: 12px; color: var(--accent); margin-bottom: 4px; }

/* 深度检索开关 */
.mode-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.deep-toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
.deep-toggle input { position: absolute; opacity: 0; width: 0; height: 0; }
.toggle-track {
  position: relative; width: 36px; height: 20px; background: var(--border);
  border-radius: 10px; transition: background 0.2s;
}
.toggle-thumb {
  position: absolute; top: 2px; left: 2px; width: 16px; height: 16px;
  background: #fff; border-radius: 50%; transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}
.deep-toggle.active .toggle-track { background: var(--accent); }
.deep-toggle.active .toggle-thumb { transform: translateX(16px); }
.toggle-label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
.deep-toggle.active .toggle-label { color: var(--accent); }
.deep-hint { font-size: 11px; color: var(--text-muted); }
.pinned-hint { font-size: 12px; color: var(--accent); margin-bottom: 4px; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.chat-input {
  flex: 1; padding: 10px 14px; border: 1px solid var(--border);
  border-radius: var(--radius); font-size: 14px; font-family: inherit;
  background: var(--bg-canvas); color: var(--text-primary); resize: none; outline: none;
}
.chat-input:focus { border-color: var(--accent); }
.btn-send, .btn-stop {
  padding: 10px 20px; border: none; border-radius: var(--radius-sm);
  font-size: 13px; font-family: inherit; cursor: pointer; flex-shrink: 0;
}
.btn-send { background: var(--accent); color: #fff; }
.btn-send:disabled { opacity: 0.4; cursor: default; }
.btn-stop { background: var(--bg-subtle); color: var(--text-secondary); border: 1px solid var(--border); }
</style>
