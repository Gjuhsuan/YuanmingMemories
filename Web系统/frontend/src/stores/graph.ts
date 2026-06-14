/**
 * Pinia：图谱探索页主状态
 */
import { defineStore } from 'pinia'
import { fetchMeta, fetchGraph, fetchNodeDetail, fetchNodeNeighbors, executeCypher } from '@/api'

export interface GraphNode {
  id: string; idKind: string; label: string; type_cn: string
  name: string; subtype_cn: string; degree: number; size: number
  color: string; date_text: string; cited: boolean
}

export interface GraphEdge {
  id: string; source: string; target: string; type: string; type_cn: string
}

export const useGraphStore = defineStore('graph', {
  state: () => ({
    meta: null as any,
    nodes: [] as GraphNode[],
    edges: [] as GraphEdge[],
    selectedId: null as string | null,
    nodeDetail: null as any,
    filters: {
      types: ['Event', 'Person', 'Place'] as string[],
      limit: 300,
      degreeMode: 'total' as 'total' | 'in' | 'out',
    },
    layout: 'force' as 'force' | 'radial' | 'dagre',
    loading: false,
    truncated: false,
    totalCandidates: 0,
  }),

  actions: {
    async loadMeta() {
      if (this.meta) return
      this.meta = await fetchMeta()
    },

    async loadGraph(params?: Record<string, any>) {
      this.loading = true
      try {
        // 同步更新 filters（保持视图状态一致）
        if (params?.types) this.filters.types = Array.isArray(params.types) ? params.types : params.types.split(',')
        if (params?.limit != null) this.filters.limit = params.limit
        if (params?.degreeMode) this.filters.degreeMode = params.degreeMode

        const p: Record<string, any> = {
          types: this.filters.types.join(','),
          limit: this.filters.limit,
          degreeMode: this.filters.degreeMode,
        }
        if (params?.centerId) { p.centerId = params.centerId; p.hops = params?.hops ?? 1 }
        const res = await fetchGraph(p)
        this.nodes = res.nodes
        this.edges = res.edges
        this.truncated = res.meta?.truncated ?? false
        this.totalCandidates = res.meta?.totalCandidates ?? 0
      } finally { this.loading = false }
    },

    // ★ 立即设 selectedId（不等 API），让 highlight 瞬间响应；API 失败再清空
    async selectNode(id: string) {
      if (id === this.selectedId) return // 双击同一节点：不清除，留给双击逻辑
      this.selectedId = id   // ← 立即响应，不等 API
      try {
        this.nodeDetail = await fetchNodeDetail(id)
      } catch (err) {
        console.error('[graph] selectNode failed:', err)
        this.selectedId = null
        this.nodeDetail = null
      }
    },

    async expandNeighbors(id: string) {
      try {
        const res = await fetchNodeNeighbors(id, 50)
        const existingIds = new Set(this.nodes.map((n) => n.id))
        for (const node of res.nodes) {
          if (!existingIds.has(node.id)) { this.nodes.push(node); existingIds.add(node.id) }
        }
        const existingEdges = new Set(this.edges.map((e) => e.id))
        for (const edge of res.edges) {
          if (!existingEdges.has(edge.id)) { this.edges.push(edge); existingEdges.add(edge.id) }
        }
      } catch (err) { console.error('[graph] expandNeighbors failed:', err) }
    },

    async runCypher(query: string) { return await executeCypher(query) },

    clearSelection() {
      this.selectedId = null
      this.nodeDetail = null
    },
  },
})
