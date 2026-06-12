<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { searchNodes } from '@/api'
import { useGraphStore } from '@/stores/graph'

const emit = defineEmits<{
  'search-select': [id: string]
  'cypher-execute': [query: string, mode: 'replace' | 'append']
}>()

const graph = useGraphStore()

const searchMode = ref<'keyword' | 'cypher'>('keyword')
const keyword = ref('')
const results = ref<any[]>([])
const showResults = ref(false)
const cypherQuery = ref('MATCH (e:Event) WHERE e.name CONTAINS "圆明园" RETURN e LIMIT 25')
const cypherMode = ref<'replace'>('replace')
let debounceTimer: any = null

// 关键词检索（防抖 300ms）
watch(keyword, (val) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!val.trim()) {
    results.value = []
    showResults.value = false
    return
  }
  debounceTimer = setTimeout(async () => {
    try {
      const res = await searchNodes(val.trim(), graph.filters.types.join(','), 20)
      results.value = res.results || []
      showResults.value = true
    } catch { results.value = [] }
  }, 300)
})

function selectResult(item: any) {
  showResults.value = false
  keyword.value = item.name
  emit('search-select', item.id)
}

function onKeyEnter() {
  if (results.value.length > 0) selectResult(results.value[0])
}

function onInputBlur() {
  setTimeout(() => { showResults.value = false }, 200)
}

function onInputFocus() {
  if (results.value.length) showResults.value = true
}

onUnmounted(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})

// Cypher 模板
const templates = [
  { name: '搜索实体', q: 'MATCH (n) WHERE n.name CONTAINS "雍正" RETURN n.name, labels(n), n.entity_type_cn LIMIT 20' },
  { name: '搜索事件', q: 'MATCH (e:Event) WHERE e.name CONTAINS "圆明园" RETURN e.name, e.event_type_cn, e.date_text LIMIT 20' },
  { name: '某人参与的事件', q: 'MATCH (p) WHERE p.name CONTAINS "雍正"\nMATCH (p)<-[r]-(e:Event)\nRETURN e.name, type(r), e.date_text ORDER BY e.date_text LIMIT 30' },
  { name: '事件因果关系', q: 'MATCH (e1:Event)-[:CAUSES]->(e2:Event)\nRETURN e1.name, e2.name LIMIT 30' },
  { name: '按类型查询', q: 'MATCH (e:Event {event_type_cn: "营造事件"})\nRETURN e.name, e.date_text LIMIT 20' },
]

function applyTemplate(q: string) {
  cypherQuery.value = q
}

async function executeCypher() {
  emit('cypher-execute', cypherQuery.value, cypherMode.value)
}
</script>

<template>
  <div class="top-bar">
    <div class="search-tabs">
      <button
        :class="{ active: searchMode === 'keyword' }"
        @click="searchMode = 'keyword'"
      >🔍 关键词</button>
      <button
        :class="{ active: searchMode === 'cypher' }"
        @click="searchMode = 'cypher'"
      >⌘ Cypher</button>
    </div>

    <!-- 关键词检索 -->
    <div v-if="searchMode === 'keyword'" class="keyword-search">
      <input
        v-model="keyword"
        type="text"
        placeholder="搜索节点名称…"
        class="search-input"
        @keydown.enter="onKeyEnter"
        @blur="onInputBlur"
        @focus="onInputFocus"
      />
      <div v-if="showResults && results.length" class="search-dropdown">
        <div
          v-for="item in results"
          :key="item.id"
          class="search-item"
          @mousedown.prevent="selectResult(item)"
        >
          <span class="si-dot" :style="{ background: item.color }"></span>
          <span class="si-name">{{ item.name }}</span>
          <span class="si-type" :style="{ color: item.color }">{{ item.type_cn }}</span>
          <span class="si-degree">度 {{ item.degree }}</span>
        </div>
      </div>
      <div v-else-if="showResults && keyword.trim() && !results.length" class="search-dropdown">
        <div class="search-empty">未找到匹配结果</div>
      </div>
    </div>

    <!-- Cypher 检索 -->
    <div v-else class="cypher-search">
      <div class="cypher-templates">
        <span class="tpl-label">模板：</span>
        <select @change="applyTemplate(($event.target as HTMLSelectElement).value)">
          <option value="">选择查询模板…</option>
          <option v-for="t in templates" :key="t.name" :value="t.q">{{ t.name }}</option>
        </select>
      </div>
      <textarea
        v-model="cypherQuery"
        class="cypher-editor"
        rows="6"
        spellcheck="false"
        placeholder="输入 Cypher 只读查询…"
      ></textarea>
      <div class="cypher-actions">
        <button class="btn-execute" @click="executeCypher">执行查询</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.top-bar {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
}

.search-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.search-tabs button {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 4px 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.search-tabs button.active {
  background: var(--bg-subtle);
  color: var(--accent);
  border-color: var(--accent);
}

.keyword-search {
  position: relative;
}

.search-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-family: inherit;
  background: var(--bg-canvas);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.15s;
}

.search-input:focus {
  border-color: var(--accent);
}

.search-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 2px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
  max-height: 300px;
  overflow-y: auto;
  z-index: 60;
}

.search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.1s;
}

.search-item:hover {
  background: var(--bg-subtle);
}

.si-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.si-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.si-type {
  font-size: 12px;
  flex-shrink: 0;
}

.si-degree {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.search-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

/* Cypher */
.cypher-templates {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.tpl-label {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.cypher-templates select {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: var(--bg-canvas);
  color: var(--text-primary);
}

.cypher-editor {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: "SF Mono", "Source Code Pro", "Roboto Mono", monospace;
  font-size: 13px;
  line-height: 1.5;
  background: var(--bg-canvas);
  color: var(--text-primary);
  resize: vertical;
  outline: none;
}

.cypher-editor:focus {
  border-color: var(--accent);
}

.cypher-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  align-items: center;
}

.btn-execute {
  padding: 6px 20px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-execute:hover {
  background: #9A3E2E;
}
</style>
