<script setup lang="ts">
/**
 * 本体结构树 —— 交互式类层次浏览。
 * 展开/折叠节点，点击查看详情，关联属性展示。
 */
import { ref, computed, onMounted } from 'vue'
import { http } from '@/api'
import { nodeColors } from '@/theme/palette'

// ── 类型 ──
interface OntoNode {
  uri: string
  label_zh: string
  label_en: string
  comment_zh: string
  comment_en: string
  parent: string | null
  children: OntoNode[]
  branch?: string  // 顶层类别，用于配色
}

interface OntoProperty {
  uri: string
  label_zh: string
  label_en: string
  comment_zh: string
  domain: string | null
  range: string | null
  inverseOf?: string | null
}

// ── 分支颜色（顶层类 → nodeColors 对应） ──
const branchColors: Record<string, string> = {
  Document: nodeColors.Document || '#7C8691',
  Actor: '#5E7A99',
  Place: nodeColors.Place || '#6E8E6A',
  Event: nodeColors.Event || '#B5503C',
  Object: nodeColors.Object || '#B08A4F',
  EventChain: nodeColors.Event || '#B5503C',
  AbstractNorm: nodeColors.AbstractNorm || '#A8836E',
  TemporalInterval: nodeColors.TemporalInterval || '#6FA0A0',
}

// ── 状态 ──
const tree = ref<OntoNode[]>([])
const objProps = ref<OntoProperty[]>([])
const dataProps = ref<OntoProperty[]>([])
const expanded = ref<Set<string>>(new Set())
const selected = ref<OntoNode | null>(null)
const loading = ref(true)

// ── 选中节点的关联属性 ──
const relatedProps = computed(() => {
  if (!selected.value) return { obj: [] as OntoProperty[], data: [] as OntoProperty[] }
  const uri = selected.value.uri
  return {
    obj: objProps.value.filter(p => p.domain === uri || p.range === uri),
    data: dataProps.value.filter(p => p.domain === uri),
  }
})

// ── 加载 ──
onMounted(async () => {
  try {
    const res = await http.get('/ontology')
    const data = res.data
    if (data.tree) {
      // 递归标注 branch
      const walk = (nodes: OntoNode[], branch: string) => {
        for (const n of nodes) {
          n.branch = branch
          if (n.children?.length) walk(n.children, branch)
        }
      }
      for (const root of data.tree) {
        walk([root], root.uri)
      }
      tree.value = data.tree
      // 默认展开第一层
      for (const n of data.tree) expanded.value.add(n.uri)
    }
    objProps.value = data.objectProperties || []
    dataProps.value = data.dataProperties || []
  } catch (e) {
    console.error('加载本体失败', e)
  } finally {
    loading.value = false
  }
})

// ── 方法 ──
function toggle(uri: string) {
  if (expanded.value.has(uri)) {
    expanded.value.delete(uri)
  } else {
    // 单击展开时，如果节点无子节点也选它
    expanded.value.add(uri)
  }
  // 强制触发响应式
  expanded.value = new Set(expanded.value)
}

function selectNode(node: OntoNode) {
  selected.value = node
}

function isExpanded(uri: string) {
  return expanded.value.has(uri)
}

function colorFor(node: OntoNode): string {
  if (node.branch && branchColors[node.branch]) return branchColors[node.branch]
  return '#9A938A'
}

function expandAll() {
  const walk = (nodes: OntoNode[]) => {
    for (const n of nodes) {
      if (n.children?.length) {
        expanded.value.add(n.uri)
        walk(n.children)
      }
    }
  }
  walk(tree.value)
  expanded.value = new Set(expanded.value)
}

function collapseAll() {
  expanded.value = new Set()
  // 保持第一层展开
  for (const n of tree.value) expanded.value.add(n.uri)
  expanded.value = new Set(expanded.value)
}

// ── 扁平化渲染（递归转扁平列表，每个节点带 depth） ──
interface FlatNode {
  node: OntoNode
  depth: number
  isLast: boolean
}
const flatList = computed<FlatNode[]>(() => {
  const result: FlatNode[] = []
  const walk = (nodes: OntoNode[], depth: number) => {
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i]
      result.push({ node: n, depth, isLast: i === nodes.length - 1 })
      if (isExpanded(n.uri) && n.children?.length) {
        walk(n.children, depth + 1)
      }
    }
  }
  walk(tree.value, 0)
  return result
})

// ── 统计 ──
const stats = computed(() => {
  let classes = 0
  let props = objProps.value.length + dataProps.value.length
  const walk = (nodes: OntoNode[]) => {
    for (const n of nodes) {
      classes++
      if (n.children?.length) walk(n.children)
    }
  }
  walk(tree.value)
  return { classes, props }
})
</script>

<template>
  <div class="ontology-tree">
    <!-- 工具栏 -->
    <div class="onto-toolbar">
      <span class="onto-title">本体结构</span>
      <span class="onto-stats">{{ stats.classes }} 类 · {{ stats.props }} 属性</span>
      <div class="onto-actions">
        <button @click="expandAll" title="全部展开">⊞</button>
        <button @click="collapseAll" title="全部折叠">⊟</button>
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="onto-loading">
      <span>⏳</span>
      <p>加载本体结构…</p>
    </div>

    <!-- 主体：树 + 详情 -->
    <div v-else class="onto-body">
      <!-- 树 -->
      <div class="onto-tree-list">
        <div
          v-for="(item, idx) in flatList"
          :key="item.node.uri"
          class="tree-row"
          :class="{
            selected: selected?.uri === item.node.uri,
            'has-children': item.node.children?.length,
            'is-root': item.depth === 0,
          }"
          :style="{ paddingLeft: (12 + item.depth * 20) + 'px' }"
          @click="selectNode(item.node)"
        >
          <!-- 展开/折叠箭头 -->
          <span
            v-if="item.node.children?.length"
            class="tree-arrow"
            @click.stop="toggle(item.node.uri)"
          >
            {{ isExpanded(item.node.uri) ? '▼' : '▶' }}
          </span>
          <span v-else class="tree-arrow placeholder"></span>

          <!-- 连线装饰 -->
          <span class="tree-line" v-if="item.depth > 0">
            <span v-if="!item.isLast">├</span>
            <span v-else>└</span>
          </span>

          <!-- 颜色圆点 -->
          <span
            class="tree-dot"
            :style="{ background: colorFor(item.node) }"
          ></span>

          <!-- 标签 -->
          <span class="tree-label-zh">{{ item.node.label_zh }}</span>
          <span class="tree-label-en">{{ item.node.label_en }}</span>

          <!-- 子类数量 -->
          <span v-if="item.node.children?.length" class="tree-badge">
            {{ item.node.children.length }}
          </span>
        </div>
      </div>

      <!-- 详情 -->
      <div v-if="selected" class="onto-detail">
        <div class="detail-bar" :style="{ background: colorFor(selected) }"></div>
        <div class="detail-body">
          <h3 class="detail-name">
            {{ selected.label_zh }}
            <span class="detail-name-en">{{ selected.label_en }}</span>
          </h3>

          <p class="detail-comment">{{ selected.comment_zh || '暂无描述。' }}</p>

          <div class="detail-meta">
            <div v-if="selected.parent" class="meta-row">
              <span class="meta-key">父类</span>
              <span class="meta-val">{{ selected.parent }}</span>
            </div>
            <div v-if="selected.children?.length" class="meta-row">
              <span class="meta-key">子类 ({{ selected.children.length }})</span>
              <span class="meta-val">
                <span
                  v-for="(ch, i) in selected.children"
                  :key="ch.uri"
                  class="child-tag"
                  :style="{ borderColor: colorFor(selected) + '66', background: colorFor(selected) + '14' }"
                >
                  {{ ch.label_zh }}
                  <template v-if="i < selected.children.length - 1">, </template>
                </span>
              </span>
            </div>
            <div class="meta-row">
              <span class="meta-key">URI</span>
              <code class="meta-code">{{ selected.uri }}</code>
            </div>
          </div>

          <!-- 关联属性 -->
          <div v-if="relatedProps.obj.length" class="related-section">
            <h4>关联对象属性</h4>
            <div v-for="p in relatedProps.obj" :key="p.uri" class="prop-chip">
              <span class="prop-name">{{ p.label_zh }}</span>
              <span class="prop-arrow">{{ p.domain === selected.uri ? '→' : '←' }}</span>
              <span class="prop-target">{{ p.domain === selected.uri ? p.range : p.domain }}</span>
            </div>
          </div>
          <div v-if="relatedProps.data.length" class="related-section">
            <h4>关联数据属性</h4>
            <div v-for="p in relatedProps.data" :key="p.uri" class="prop-chip">
              <span class="prop-name">{{ p.label_zh }}</span>
              <span class="prop-type">: {{ p.range || 'string' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 无选中 -->
      <div v-else class="onto-detail empty-detail">
        <span>📐</span>
        <p>点击左侧类名查看详情</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ontology-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── 工具栏 ── */
.onto-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.onto-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.onto-stats {
  font-size: 11px;
  color: var(--text-muted);
  flex: 1;
}
.onto-actions {
  display: flex;
  gap: 4px;
}
.onto-actions button {
  width: 24px;
  height: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  font-size: 12px;
  cursor: pointer;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.onto-actions button:hover {
  color: var(--accent);
  border-color: var(--accent);
}

/* ── 加载 ── */
.onto-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 13px;
}
.onto-loading span { font-size: 24px; opacity: 0.5; }

/* ── 主体 ── */
.onto-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 树列表 ── */
.onto-tree-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}
.tree-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 16px 5px 12px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.1s;
  user-select: none;
  min-height: 30px;
}
.tree-row:hover {
  background: var(--bg-subtle);
}
.tree-row.selected {
  background: var(--accent) + '14';
  outline: 1px solid var(--accent) + '33';
  outline-offset: -1px;
  border-radius: var(--radius-sm);
}
.tree-row.is-root {
  font-weight: 500;
}

.tree-arrow {
  width: 16px;
  font-size: 9px;
  color: var(--text-muted);
  flex-shrink: 0;
  text-align: center;
  transition: transform 0.15s;
}
.tree-arrow.placeholder { visibility: hidden; }

.tree-line {
  width: 16px;
  font-size: 10px;
  color: var(--border);
  flex-shrink: 0;
  text-align: center;
  font-family: monospace;
}

.tree-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  opacity: 0.85;
}

.tree-label-zh {
  color: var(--text-primary);
  white-space: nowrap;
}
.tree-label-en {
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tree-badge {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  border-radius: 8px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}

/* ── 详情 ── */
.onto-detail {
  flex-shrink: 0;
  border-top: 2px solid var(--border);
  max-height: 45%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.onto-detail.empty-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  color: var(--text-muted);
  font-size: 13px;
  gap: 8px;
}
.onto-detail.empty-detail span { font-size: 28px; opacity: 0.4; }

.detail-bar {
  height: 3px;
  flex-shrink: 0;
}
.detail-body {
  padding: 14px 16px;
}
.detail-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}
.detail-name-en {
  font-weight: 400;
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 6px;
}
.detail-comment {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0 0 12px;
}

.detail-meta {
  margin-bottom: 12px;
}
.meta-row {
  display: flex;
  padding: 3px 0;
  font-size: 12px;
}
.meta-key {
  color: var(--text-muted);
  width: 80px;
  flex-shrink: 0;
}
.meta-val {
  color: var(--text-secondary);
}
.meta-code {
  font-family: 'Roboto Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 1px 4px;
  border-radius: 2px;
}
.child-tag {
  font-size: 11px;
  border: 1px solid;
  border-radius: 2px;
  padding: 0 4px;
}

.related-section {
  margin-bottom: 12px;
}
.related-section h4 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 6px;
}
.prop-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  font-size: 12px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  margin-bottom: 4px;
}
.prop-name {
  color: var(--text-primary);
  font-weight: 500;
}
.prop-arrow {
  color: var(--text-muted);
  font-size: 11px;
}
.prop-target {
  color: var(--accent);
}
.prop-type {
  color: var(--text-muted);
  font-size: 11px;
}
</style>
