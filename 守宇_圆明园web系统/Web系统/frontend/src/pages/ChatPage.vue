<script setup lang="ts">
/**
 * 页面②：AI 问答 —— 左对话 + 右 RAG 子图
 *
 * Fix3: 双击 RAG 子图节点 → 展示所有类型邻居
 * Fix4: 引用点击 → 高亮 RAG 子图节点
 */
import { ref, computed, watch, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useContextStore } from '@/stores/context'
import ChatPanel from '@/components/ChatPanel.vue'
import GraphCanvas from '@/components/GraphCanvas.vue'
import { nodeColors } from '@/theme/palette'
import { fetchNodeNeighbors } from '@/api'

const chat = useChatStore()
const context = useContextStore()

// 离开页面时停止流式请求
onUnmounted(() => {
  chat.stop()
})
const ragCanvasRef = ref<InstanceType<typeof GraphCanvas>>()

// 用于 RAG 子图内双击展开的增强数据
const ragHighlightId = ref<string | null>(null)

function sendQuestion(q: string) {
  ragHighlightId.value = null
  chat.ask(q)
}

function stop() {
  chat.stop()
}

// Fix4: 引用点击 → 在 RAG 子图中高亮对应节点
function onCitationClick(nodeId: string) {
  ragHighlightId.value = nodeId
  if (!chat.citedIds.includes(nodeId)) {
    chat.citedIds.push(nodeId)
  }
}

// Fix3: 双击 RAG 子图节点 → 展开所有类型邻居
async function onRagNodeDblClick(node: any) {
  try {
    const res = await fetchNodeNeighbors(node.id, 30)
    if (res?.nodes?.length) {
      const existingIds = new Set(chat.ragGraph?.nodes?.map((n: any) => n.id) || [])
      const newNodes = [...(chat.ragGraph?.nodes || [])]
      const newEdges = [...(chat.ragGraph?.edges || [])]
      if (chat.ragGraph) {
        for (const n of res.nodes) {
          if (!existingIds.has(n.id)) {
            newNodes.push(n)
            existingIds.add(n.id)
          }
        }
        const existingEdges = new Set(newEdges.map((e: any) => e.id))
        for (const e of (res.edges || [])) {
          if (!existingEdges.has(e.id)) {
            newEdges.push(e)
            existingEdges.add(e.id)
          }
        }
        // 创建新对象引用，触发 Vue 响应式更新
        chat.ragGraph = { nodes: newNodes, edges: newEdges }
      }
      ragHighlightId.value = node.id
    }
  } catch { /* ignore */ }
}

function addToContext(node: any) {
  context.addItem({
    id: node.id,
    idKind: node.idKind || 'entity',
    name: node.name,
    label: node.label,
    type_cn: node.type_cn,
    color: nodeColors[node.label] || '#9A938A',
    addedFrom: 'chat',
  })
}

const ragNodes = computed(() => chat.ragGraph?.nodes || [])
const ragEdges = computed(() => chat.ragGraph?.edges || [])
</script>

<template>
  <div class="chat-page">
    <div class="chat-left">
      <ChatPanel
        :messages="chat.messages"
        :streaming="chat.streaming"
        :pinned-count="context.count"
        :error="chat.error"
        :deep-mode="chat.deepMode"
        :rag-steps="chat.graphRAGSteps"
        :rag-active="chat.graphRAGActive"
        @send="sendQuestion"
        @stop="stop"
        @citation-click="onCitationClick"
        @toggle-deep="chat.deepMode = $event"
      />
    </div>

    <div class="chat-right">
      <div class="rag-header">
        <h3>本轮检索子图</h3>
        <span class="rag-count">{{ ragNodes.length }} 节点</span>
      </div>

      <div class="rag-canvas">
        <GraphCanvas
          v-if="ragNodes.length > 0"
          ref="ragCanvasRef"
          :nodes="ragNodes"
          :edges="ragEdges"
          mode="rag"
          :highlight-id="ragHighlightId"
          :cited-ids="chat.citedIds"
          @node-dblclick="onRagNodeDblClick"
          @add-context="addToContext"
        />
        <div v-if="ragNodes.length === 0" class="rag-empty">
          <span>◉</span>
          <p>提出一个问题，这里将展示<br>AI 检索所用的图谱证据</p>
        </div>
      </div>

      <div class="rag-legend">
        <div v-for="(color, label) in nodeColors" :key="label" class="rl-item">
          <span class="rl-dot" :style="{ background: color }"></span>
          <span class="rl-name">{{ label === 'Event' ? '事件' : label === 'Person' ? '人物' :
            label === 'Place' ? '地点' : label === 'Organization' ? '机构' :
            label === 'Object' ? '客体' : label === 'Document' ? '文献' :
            label === 'AbstractNorm' ? '抽象规范' : '时间区间' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page { display: flex; height: 100%; overflow: hidden; }
.chat-left { flex: 1; min-width: 0; border-right: 1px solid var(--border); }
.chat-right { width: 380px; display: flex; flex-direction: column; background: var(--bg-panel); flex-shrink: 0; }
.rag-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.rag-header h3 { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.rag-count { font-size: 12px; color: var(--text-muted); }
.rag-canvas { flex: 1; min-height: 0; position: relative; }
.rag-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: var(--text-muted); }
.rag-empty span { font-size: 32px; opacity: 0.4; margin-bottom: 12px; }
.rag-empty p { font-size: 13px; line-height: 1.8; }
.rag-legend { display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 16px; border-top: 1px solid var(--border); flex-shrink: 0; }
.rl-item { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.rl-dot { width: 8px; height: 8px; border-radius: 50%; }
.rl-name { color: var(--text-secondary); }
</style>
