/**
 * Pinia：AI 问答页状态。
 * 支持 SimpleRAG 和 GraphRAG 深度检索两种模式。
 */
import { defineStore } from 'pinia'
import { streamChat, streamGraphRAG, type SSEEvent } from '@/api/chat'
import { useContextStore } from './context'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations?: { id: string; marker: string }[]
  retrievalGraph?: { nodes: any[]; edges: any[] }
}

export interface GraphRAGStep {
  id: string
  label: string
  icon: string
  status: 'pending' | 'active' | 'done' | 'retry'
  detail: string
  meta?: string
}

export const useChatStore = defineStore('chat', {
  state: () => ({
    sessionId: null as string | null,
    messages: [] as ChatMessage[],
    streaming: false,
    ragGraph: null as { nodes: any[]; edges: any[] } | null,
    citedIds: [] as string[],
    error: null as string | null,
    abortCtrl: null as AbortController | null,
    // GraphRAG 深度检索
    deepMode: false,
    graphRAGSteps: [] as GraphRAGStep[],
    graphRAGActive: false,
  }),

  actions: {
    // ── 通用发送入口 ──
    async ask(question: string) {
      if (this.streaming) return
      if (this.deepMode) {
        await this._askGraphRAG(question)
      } else {
        await this._askSimple(question)
      }
    },

    // ── SimpleRAG ──
    async _askSimple(question: string) {
      const contextStore = useContextStore()
      const pinnedIds = contextStore.pinnedIds

      const history = this.messages.slice(-12).map(m => ({ role: m.role, content: m.content }))

      this.streaming = true; this.error = null; this.ragGraph = null; this.citedIds = []
      this.graphRAGActive = false; this.graphRAGSteps = []
      this.messages.push({ role: 'user', content: question })
      const aiMsg: ChatMessage = { role: 'assistant', content: '', citations: [] }
      this.messages.push(aiMsg)
      this.abortCtrl = new AbortController()

      try {
        for await (const sse of streamChat(
          { sessionId: this.sessionId, question, pinnedNodeIds: pinnedIds, history },
          this.abortCtrl.signal,
        )) {
          if (sse.event === 'session') this.sessionId = sse.data.sessionId
          else if (sse.event === 'retrieval') {
            this.ragGraph = sse.data.graph
            aiMsg.retrievalGraph = sse.data.graph
          } else if (sse.event === 'token') aiMsg.content += sse.data.text || ''
          else if (sse.event === 'citation') {
            if (sse.data.nodeIds) {
              for (const nid of sse.data.nodeIds) {
                if (!this.citedIds.includes(nid)) this.citedIds.push(nid)
              }
            }
            if (!aiMsg.citations) aiMsg.citations = []
            aiMsg.citations.push(sse.data)
          } else if (sse.event === 'error') this.error = sse.data.message || '未知错误'
          this._syncMsg(aiMsg)
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          this.error = err.message || '请求失败'
          aiMsg.content = aiMsg.content || `（错误：${this.error}）`
        }
      } finally {
        this.streaming = false; this.abortCtrl = null
      }
    },

    // ── GraphRAG 深度检索 ──
    async _askGraphRAG(question: string) {
      const contextStore = useContextStore()
      const pinnedIds = contextStore.pinnedIds
      const history = this.messages.slice(-12).map(m => ({ role: m.role, content: m.content }))

      this.streaming = true; this.error = null; this.ragGraph = null; this.citedIds = []
      this.graphRAGActive = true
      this.graphRAGSteps = this._initSteps()

      this.messages.push({ role: 'user', content: question })
      const aiMsg: ChatMessage = { role: 'assistant', content: '', citations: [] }
      this.messages.push(aiMsg)
      this.abortCtrl = new AbortController()

      try {
        for await (const sse of streamGraphRAG(
          { sessionId: this.sessionId, question, pinnedNodeIds: pinnedIds, history },
          this.abortCtrl.signal,
        )) {
          this._handleGraphRAGSSE(sse, aiMsg)
          this._syncMsg(aiMsg)
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          this.error = err.message || '请求失败'
          aiMsg.content = aiMsg.content || `（错误：${this.error}）`
        }
      } finally {
        this.streaming = false; this.abortCtrl = null; this.graphRAGActive = false
        this._markAllStepsDone()
      }
    },

    _retrievalCount: 0,
    _reflectCount: 0,

    _initSteps(): GraphRAGStep[] {
      this._retrievalCount = 0
      this._reflectCount = 0
      return []
    },

    _addStep(id: string, icon: string, label: string, status: 'active'|'done'|'retry', detail = '', meta = '') {
      // 构建新数组确保 Vue 响应式检测到变化
      const steps = this.graphRAGSteps.map(s => ({ ...s }))

      // 查找同 id 同 status 的步骤 → 更新
      const existingIdx = steps.findIndex(s => s.id === id && s.status === status)
      if (existingIdx >= 0) {
        if (detail) steps[existingIdx].detail = detail
        if (meta) steps[existingIdx].meta = meta
        this.graphRAGSteps = steps
        return
      }

      // 查找同 id 状态为 active 的步骤 → 更新为 done/retry
      const activeIdx = steps.findIndex(s => s.id === id && s.status === 'active')
      if (activeIdx >= 0 && status !== 'active') {
        steps[activeIdx].status = status
        if (detail) steps[activeIdx].detail = detail
        if (meta) steps[activeIdx].meta = meta
        this.graphRAGSteps = steps
        return
      }

      // 新步骤
      steps.push({ id, icon, label, status, detail, meta })
      this.graphRAGSteps = steps
    },

    _markAllStepsDone() {
      const steps = this.graphRAGSteps.map(s => ({ ...s, status: s.status === 'active' ? 'done' as const : s.status }))
      this.graphRAGSteps = steps
    },

    _handleGraphRAGSSE(sse: SSEEvent, aiMsg: ChatMessage) {
      switch (sse.event) {
        case 'plan':
          if (sse.data.stage === 'decompose') {
            this._addStep('plan', '🧠', '问题规划', 'active', sse.data.message || '正在分解问题...')
          } else {
            const sqs = sse.data.subquestions || []
            this._addStep('plan', '🧠', '问题规划', 'done', `${sse.data.task_type || ''}`, `${sqs.length}个子问题`)
          }
          break

        case 'retrieve_start': {
          this._retrievalCount++
          const rid = `retrieve_${this._retrievalCount}`
          const sq = sse.data.question || ''
          this._addStep(rid, '🔍', `检索 · 子问题${sse.data.sub_idx}/${sse.data.total}`, 'active', sq)
          break
        }

        case 'retrieve_done': {
          const rid = `retrieve_${this._retrievalCount}`
          const kept = sse.data.kept_events || 0
          const total = sse.data.candidate_events || 0
          const seeds = (sse.data.seed_entities?.length || 0) + (sse.data.seed_events?.length || 0)
          // 上一步检索 done
          this._addStep(rid, '🔍', `检索 · 子问题${sse.data.sub_idx}/${sse.data.total}`, 'done',
            '', `种子×${seeds} 命中${kept}/${total}`)
          break
        }

        case 'reflection':
          if (sse.data.stage === 'thinking') {
            this._reflectCount++
            const fid = `reflect_${this._reflectCount}`
            this._addStep(fid, '🔄', `反思 · 第${sse.data.iteration}轮`, 'active',
              `评估证据充分性...`)
          } else {
            const fid = `reflect_${this._reflectCount}`
            const enough = sse.data.enough
            const status = enough ? 'done' : 'retry'
            const msg = enough
              ? `证据充分，可以作答`
              : `证据不足：${(sse.data.missing_aspects || []).join('；') || '需补充检索'}`
            this._addStep(fid, '🔄', `反思 · 第${sse.data.iteration}轮`, status, msg)
          }
          break

        case 'support_graph':
          // ★ 推送到本轮检索子图（需规范化 GraphRAG 的节点格式为 GraphCanvas 格式）
          if (sse.data.graph) {
            const raw = sse.data.graph
            const GROUP_COLORS: Record<string, string> = {
              Event: '#B5503C', Person: '#5E7A99', Place: '#6E8E6A',
              Organization: '#8E7BA0', Document: '#7C8691', Object: '#B08A4F',
              AbstractNorm: '#A8836E', TemporalInterval: '#6FA0A0',
              Community: '#9A938A', Entity: '#9A938A',
            }
            const normalized = {
              nodes: (raw.nodes || []).map((n: any) => ({
                id: n.id,
                idKind: n.group === 'Event' ? 'event' : 'entity',
                label: n.group || 'Entity',
                type_cn: n.type_cn || n.group || '',
                name: n.label || n.id,
                color: GROUP_COLORS[n.group] || '#9A938A',
                size: 24,
                degree: 0,
                date_text: '',
                cited: false,
                subtype_cn: '',
              })),
              edges: (raw.edges || []).map((e: any) => ({
                id: `${e.from || e.source}-${e.to || e.target}-${e.label || ''}`,
                source: e.from || e.source,
                target: e.to || e.target,
                type: e.label || '',
                type_cn: e.label || '',
              })),
            }
            this.ragGraph = normalized
            aiMsg.retrievalGraph = normalized
          }
          break

        case 'answer':
          if (sse.data.stage === 'synthesizing') {
            this._addStep('answer', '💬', '答案合成', 'active', '正在综合证据生成答案...')
          } else if (sse.data.stage === 'verifying') {
            this._addStep('answer', '💬', '答案合成', 'active', '正在验证答案准确性...')
          } else if (sse.data.stage === 'done') {
            this._addStep('answer', '💬', '答案合成', 'done', '', '完成')
            aiMsg.content = sse.data.text || ''
          }
          break

        case 'slots':
          break

        case 'error':
          this.error = sse.data.message || '未知错误'
          break

        case 'done':
          this._markAllStepsDone()
          break
      }
    },

    _syncMsg(msg: ChatMessage) {
      const idx = this.messages.length - 1
      if (idx >= 0 && this.messages[idx].role === 'assistant') {
        this.messages.splice(idx, 1, { ...msg, citations: msg.citations ? [...msg.citations] : [] })
      }
    },

    stop() {
      if (this.abortCtrl) { this.abortCtrl.abort(); this.abortCtrl = null }
      this.streaming = false
    },

    reset() {
      this.stop()
      this.sessionId = null; this.messages = []; this.ragGraph = null
      this.citedIds = []; this.error = null
      this.graphRAGSteps = []; this.graphRAGActive = false
    },
  },
})
