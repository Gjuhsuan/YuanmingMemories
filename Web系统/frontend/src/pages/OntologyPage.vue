<script setup lang="ts">
/**
 * 页面③：本体结构 —— 交互式类层次浏览。
 * 左侧类层次树，右侧选中类的详情与关联属性。
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
  branch?: string
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

// ── 分支颜色 ──
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
    const { data } = await http.get('/ontology')
    if (data.tree) {
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
      // 默认展开所有
      const allUris = new Set<string>()
      const collect = (nodes: OntoNode[]) => {
        for (const n of nodes) {
          if (n.children?.length) allUris.add(n.uri)
          if (n.children?.length) collect(n.children)
        }
      }
      collect(data.tree)
      expanded.value = allUris
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
  if (expanded.value.has(uri)) expanded.value.delete(uri)
  else expanded.value.add(uri)
  expanded.value = new Set(expanded.value)
}
function selectNode(node: OntoNode) {
  selected.value = node
}
function isExpanded(uri: string) { return expanded.value.has(uri) }
function colorFor(node: OntoNode): string {
  return branchColors[node.branch || ''] || '#9A938A'
}
function expandAll() {
  const all = new Set<string>()
  const walk = (nodes: OntoNode[]) => {
    for (const n of nodes) {
      if (n.children?.length) { all.add(n.uri); walk(n.children) }
    }
  }
  walk(tree.value)
  expanded.value = all
}
function collapseAll() {
  expanded.value = new Set()
}

// ── 将类名映射为中文 ──
const classLabelMap = computed(() => {
  const map: Record<string, string> = {}
  const walk = (nodes: OntoNode[]) => {
    for (const n of nodes) {
      map[n.uri] = n.label_zh
      if (n.children?.length) walk(n.children)
    }
  }
  walk(tree.value)
  return map
})

function getLabel(uri: string | null): string {
  if (!uri) return ''
  return classLabelMap.value[uri] || uri
}

// ── 扁平化渲染 ──
interface FlatNode { node: OntoNode; depth: number }
const flatList = computed<FlatNode[]>(() => {
  const result: FlatNode[] = []
  const walk = (nodes: OntoNode[], depth: number) => {
    for (const n of nodes) {
      result.push({ node: n, depth })
      if (isExpanded(n.uri) && n.children?.length) walk(n.children, depth + 1)
    }
  }
  walk(tree.value, 0)
  return result
})

const stats = computed(() => {
  let classes = 0
  const walk = (nodes: OntoNode[]) => {
    for (const n of nodes) { classes++; if (n.children?.length) walk(n.children) }
  }
  walk(tree.value)
  return { classes, objProps: objProps.value.length, dataProps: dataProps.value.length }
})
</script>

<template>
  <div class="ontology-page">
    <!-- 加载 -->
    <div v-if="loading" class="loading-state">
      <span>⏳</span>
      <p>加载本体结构…</p>
    </div>

    <template v-else>
      <!-- 左侧：类层次树 -->
      <aside class="onto-left">
        <div class="onto-left-header">
          <h2>类层次</h2>
          <span class="stat-badge">{{ stats.classes }} 类</span>
          <div class="header-actions">
            <button @click="expandAll" title="全部展开">⊞</button>
            <button @click="collapseAll" title="全部折叠">⊟</button>
          </div>
        </div>
        <div class="tree-scroll">
          <div
            v-for="item in flatList"
            :key="item.node.uri"
            class="tree-row"
            :class="{
              selected: selected?.uri === item.node.uri,
              root: item.depth === 0,
            }"
            :style="{ paddingLeft: (16 + item.depth * 24) + 'px' }"
            @click="selectNode(item.node)"
          >
            <!-- 展开/折叠 -->
            <span
              v-if="item.node.children?.length"
              class="tree-toggle"
              @click.stop="toggle(item.node.uri)"
            >{{ isExpanded(item.node.uri) ? '▾' : '▸' }}</span>
            <span v-else class="tree-toggle spacer"></span>

            <!-- 分支线 -->
            <span class="tree-branch" v-if="item.depth > 0">└</span>

            <!-- 颜色点 -->
            <span class="tree-dot" :style="{ background: colorFor(item.node) }"></span>

            <!-- 标签 -->
            <span class="tree-zh">{{ item.node.label_zh }}</span>
            <span class="tree-en">{{ item.node.label_en }}</span>

            <!-- 子类数 -->
            <span v-if="item.node.children?.length" class="tree-count">
              {{ item.node.children.length }}
            </span>
          </div>
        </div>
      </aside>

      <!-- 右侧：详情 -->
      <section class="onto-right">
        <template v-if="selected">
          <!-- 顶部色条 -->
          <div class="detail-accent" :style="{ background: colorFor(selected) }"></div>

          <div class="detail-scroll">
            <!-- 标题 -->
            <div class="detail-header">
              <h2 class="detail-name">
                {{ selected.label_zh }}
                <span class="detail-name-en">{{ selected.label_en }}</span>
              </h2>
              <span
                class="detail-branch-tag"
                :style="{ background: colorFor(selected) + '18', color: colorFor(selected), borderColor: colorFor(selected) + '40' }"
              >
                {{ getLabel(selected.branch || '') }}
              </span>
            </div>

            <!-- 描述 -->
            <p class="detail-desc">{{ selected.comment_zh || '暂无描述。' }}</p>
            <p v-if="selected.comment_en" class="detail-desc-en">{{ selected.comment_en }}</p>

            <!-- 元信息 -->
            <div class="detail-meta">
              <div class="meta-item" v-if="selected.parent">
                <span class="meta-label">父类</span>
                <span class="meta-value link">{{ getLabel(selected.parent) }}</span>
              </div>
              <div class="meta-item" v-if="selected.children?.length">
                <span class="meta-label">子类</span>
                <span class="meta-value">
                  <span
                    v-for="ch in selected.children"
                    :key="ch.uri"
                    class="child-chip"
                    :style="{
                      background: colorFor(selected) + '12',
                      borderColor: colorFor(selected) + '30',
                      color: colorFor(selected),
                    }"
                  >{{ ch.label_zh }}</span>
                </span>
              </div>
              <div class="meta-item">
                <span class="meta-label">URI</span>
                <code class="meta-uri">:{{ selected.uri }}</code>
              </div>
            </div>

            <!-- 关联对象属性 -->
            <div v-if="relatedProps.obj.length" class="props-block">
              <h3 class="props-title">
                关联对象属性
                <span class="props-count">{{ relatedProps.obj.length }}</span>
              </h3>
              <div class="prop-list">
                <div v-for="p in relatedProps.obj" :key="p.uri" class="prop-card">
                  <div class="prop-card-header">
                    <span class="prop-card-name">{{ p.label_zh }}</span>
                    <code class="prop-card-uri">:{{ p.uri }}</code>
                  </div>
                  <p class="prop-card-comment">{{ p.comment_zh }}</p>
                  <div class="prop-card-signature">
                    <span class="sig-item domain" :style="{ color: colorFor(selected) }">
                      {{ getLabel(p.domain) }}
                    </span>
                    <span class="sig-arrow">
                      {{ p.domain === selected.uri ? '→' : '←' }}
                    </span>
                    <span class="sig-item range" :style="{ color: branchColors[p.range || ''] || '#9A938A' }">
                      {{ getLabel(p.range) }}
                    </span>
                    <span v-if="p.inverseOf" class="sig-inverse">
                      (逆: :{{ p.inverseOf }})
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 关联数据属性 -->
            <div v-if="relatedProps.data.length" class="props-block">
              <h3 class="props-title">
                关联数据属性
                <span class="props-count">{{ relatedProps.data.length }}</span>
              </h3>
              <div class="prop-list">
                <div v-for="p in relatedProps.data" :key="p.uri" class="prop-card data-prop">
                  <div class="prop-card-header">
                    <span class="prop-card-name">{{ p.label_zh }}</span>
                    <code class="prop-card-uri">:{{ p.uri }}</code>
                  </div>
                  <p class="prop-card-comment">{{ p.comment_zh }}</p>
                  <div class="prop-card-signature">
                    <span class="sig-type">范围: {{ p.range || 'string' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 无关联属性 -->
            <div v-if="!relatedProps.obj.length && !relatedProps.data.length" class="no-props">
              该类暂无直接关联的属性定义。
            </div>
          </div>
        </template>

        <!-- 空状态 -->
        <div v-else class="empty-right">
          <span class="empty-icon">📐</span>
          <h2>圆明园事件知识图谱本体</h2>
          <p>基于 CIDOC CRM 参考模型设计</p>
          <div class="empty-stats">
            <div class="estat">
              <span class="estat-num">{{ stats.classes }}</span>
              <span class="estat-label">类</span>
            </div>
            <div class="estat">
              <span class="estat-num">{{ stats.objProps }}</span>
              <span class="estat-label">对象属性</span>
            </div>
            <div class="estat">
              <span class="estat-num">{{ stats.dataProps }}</span>
              <span class="estat-label">数据属性</span>
            </div>
          </div>
          <p class="empty-hint">← 点击左侧类名查看详情</p>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.ontology-page {
  display: flex;
  height: 100%;
  overflow: hidden;
}

/* ── 加载 ── */
.loading-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-muted);
}
.loading-state span { font-size: 32px; opacity: 0.5; }

/* ── 左侧 ── */
.onto-left {
  width: 380px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex;
  flex-direction: column;
}
.onto-left-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--bg-subtle);
  flex-shrink: 0;
}
.onto-left-header h2 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.stat-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 2px 8px;
  border-radius: 8px;
}
.header-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.header-actions button {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.header-actions button:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.tree-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

/* 树节点 */
.tree-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 20px 6px 16px;
  cursor: pointer;
  transition: background 0.1s;
  user-select: none;
  min-height: 32px;
}
.tree-row:hover { background: var(--bg-subtle); }
.tree-row.selected {
  background: #B5503C0E;
  box-shadow: inset 3px 0 0 var(--accent);
}
.tree-row.root { font-weight: 500; }

.tree-toggle {
  width: 16px;
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
  text-align: center;
}
.tree-toggle.spacer { visibility: hidden; }

.tree-branch {
  width: 12px;
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

.tree-zh {
  color: var(--text-primary);
  white-space: nowrap;
  font-size: 13px;
}
.tree-en {
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-left: 4px;
}

.tree-count {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  border-radius: 8px;
  padding: 1px 6px;
  min-width: 18px;
  text-align: center;
}

/* ── 右侧 ── */
.onto-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-canvas);
}
.detail-accent {
  height: 4px;
  flex-shrink: 0;
}
.detail-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
}

/* 标题 */
.detail-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.detail-name {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.detail-name-en {
  font-weight: 400;
  font-size: 14px;
  color: var(--text-muted);
  margin-left: 8px;
}
.detail-branch-tag {
  font-size: 12px;
  padding: 2px 10px;
  border: 1px solid;
  border-radius: 12px;
  white-space: nowrap;
}

/* 描述 */
.detail-desc {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin: 0 0 8px;
  max-width: 700px;
}
.detail-desc-en {
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
  line-height: 1.6;
  margin: 0 0 20px;
}

/* 元信息 */
.detail-meta {
  margin-bottom: 28px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.meta-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 13px;
}
.meta-label {
  color: var(--text-muted);
  width: 48px;
  flex-shrink: 0;
  padding-top: 2px;
}
.meta-value {
  color: var(--text-secondary);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.meta-uri {
  font-family: 'Roboto Mono', monospace;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 2px 8px;
  border-radius: 3px;
}
.child-chip {
  font-size: 12px;
  padding: 2px 8px;
  border: 1px solid;
  border-radius: 4px;
}

/* 属性区块 */
.props-block {
  margin-bottom: 24px;
}
.props-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.props-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 1px 8px;
  border-radius: 8px;
}

.prop-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.prop-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 18px;
  transition: border-color 0.15s;
  max-width: 700px;
}
.prop-card:hover {
  border-color: var(--accent) + '40';
}
.prop-card-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}
.prop-card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.prop-card-uri {
  font-family: 'Roboto Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
}
.prop-card-comment {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 8px;
}
.prop-card-signature {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.sig-item {
  font-weight: 500;
}
.sig-item.domain { }
.sig-item.range { }
.sig-arrow {
  color: var(--text-muted);
  font-size: 16px;
}
.sig-inverse {
  font-size: 11px;
  color: var(--text-muted);
}
.sig-type {
  font-size: 12px;
  color: var(--text-muted);
}

/* 无属性提示 */
.no-props {
  font-size: 13px;
  color: var(--text-muted);
  padding: 20px 0;
}

/* ── 空右侧 ── */
.empty-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--text-secondary);
}
.empty-icon { font-size: 48px; opacity: 0.35; margin-bottom: 16px; }
.empty-right h2 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}
.empty-right p { font-size: 14px; color: var(--text-muted); margin: 0 0 20px; }
.empty-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
}
.estat {
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 24px;
  min-width: 100px;
}
.estat-num {
  font-size: 28px;
  font-weight: 600;
  color: var(--accent);
  font-family: 'Roboto Mono', monospace;
}
.estat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}
.empty-hint {
  font-size: 13px !important;
  color: var(--text-muted) !important;
}
</style>
