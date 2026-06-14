<script setup lang="ts">
import { ref, watch } from 'vue'
import { useContextStore } from '@/stores/context'
import { nodeColors } from '@/theme/palette'

const props = defineProps<{
  detail: any | null
  loading: boolean
}>()

const emit = defineEmits<{
  'add-context': [node: any]
  'locate': [id: string]
  'center': [id: string]
}>()

const context = useContextStore()
const collapsed = ref(false)
const expandReasoning = ref(false)

// 档案影像状态
const archivePage = ref<number | null>(null)
const archiveImageUrl = ref<string | null>(null)
const archiveTotalPages = ref(0)
const archiveLoading = ref(false)
const archiveError = ref('')

async function fetchArchivePage(sourceText: string) {
  archiveLoading.value = true
  archiveError.value = ''
  archivePage.value = null
  archiveImageUrl.value = null

  try {
    const resp = await fetch('/api/archive/locate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sourceText }),
    })
    if (!resp.ok) {
      archiveError.value = '档案影像接口异常'
      return
    }
    const data = await resp.json()
    archiveTotalPages.value = data.totalPages

    if (data.hasMatch && data.page) {
      archivePage.value = data.page
      archiveImageUrl.value = data.imageUrl
    }
  } catch {
    archiveError.value = '无法连接档案影像服务'
  } finally {
    archiveLoading.value = false
  }
}

// 在详情切换时请求匹配
watch(
  () => props.detail?.sourceText,
  (text) => {
    if (text) {
      fetchArchivePage(text)
    } else {
      archivePage.value = null
      archiveImageUrl.value = null
      archiveError.value = ''
    }
  }
)

function addToContext() {
  if (!props.detail) return
  emit('add-context', {
    id: props.detail.id,
    idKind: props.detail.idKind,
    name: props.detail.name,
    label: props.detail.label,
    type_cn: props.detail.type_cn,
    color: nodeColors[props.detail.label] || '#9A938A',
    addedFrom: 'explore' as const,
  })
}

function isInContext(id: string): boolean {
  return context.items.some((i) => i.id === id)
}
</script>

<template>
  <aside class="left-archive" :class="{ collapsed }">
    <!-- 折叠把手 -->
    <button class="collapse-handle" @click="collapsed = !collapsed" :title="collapsed ? '展开' : '折叠'">
      {{ collapsed ? '▶' : '◀' }}
    </button>

    <div v-if="!collapsed" class="archive-content">
      <!-- 加载骨架 -->
      <div v-if="loading" class="skeleton">
        <div class="sk-line w-60"></div>
        <div class="sk-line w-40"></div>
        <div class="sk-line w-80"></div>
        <div class="sk-line w-50"></div>
        <div class="sk-line w-full"></div>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!detail" class="empty">
        <div class="empty-icon">📋</div>
        <p>请在图中点击一个节点</p>
        <p class="empty-sub">以查看其档案与属性</p>
      </div>

      <!-- 节点详情 -->
      <template v-else>
        <!-- 标题区 -->
        <div class="detail-header">
          <h2 class="node-name">{{ detail.name }}</h2>
          <div class="node-tags">
            <span
              class="type-tag"
              :style="{
                background: (nodeColors[detail.label] || '#9A938A') + '1F',
                color: nodeColors[detail.label] || '#9A938A',
                borderColor: nodeColors[detail.label] || '#9A938A',
              }"
            >
              {{ detail.type_cn }}
            </span>
            <span v-if="detail.subtype_cn" class="subtype">{{ detail.subtype_cn }}</span>
            <span class="degree">度数 {{ detail.degree }}</span>
          </div>
        </div>

        <!-- 操作按钮组 -->
        <div class="action-buttons">
          <button class="btn-center" @click="emit('center', detail.id)">
            ⊙ 以此为中心
          </button>
          <button
            class="btn-context"
            @click="addToContext"
            :disabled="isInContext(detail.id)"
          >
            {{ isInContext(detail.id) ? '已在上下文篮中' : '＋ 加入 AI 上下文' }}
          </button>
        </div>

        <!-- 档案影像 -->
        <div class="image-section">
          <h3 class="section-title">档案影像</h3>

          <!-- 加载中 -->
          <div v-if="archiveLoading" class="img-loading">
            <span>🔍</span>
            <p>正在匹配档案页面…</p>
          </div>

          <!-- 错误 -->
          <div v-else-if="archiveError" class="img-error">
            <span>⚠️</span>
            <p>{{ archiveError }}</p>
          </div>

          <!-- 已匹配 -->
          <div v-else-if="archiveImageUrl" class="img-container">
            <img
              :src="archiveImageUrl"
              :alt="`档案第 ${archivePage} 页`"
              class="archive-image"
            />
            <div class="img-caption">
              第 {{ archivePage }} / {{ archiveTotalPages }} 页
            </div>
          </div>

          <!-- 无匹配 -->
          <div v-else class="img-placeholder-box">
            <span>📷</span>
            <p>未能匹配到档案影像</p>
          </div>
        </div>

        <!-- 原档案文本 -->
        <div v-if="detail.sourceText" class="source-section">
          <h3 class="section-title">原档案文本</h3>
          <div class="source-text">
            {{ detail.sourceText }}
          </div>
        </div>

        <!-- 属性列表 -->
        <div class="props-section">
          <h3 class="section-title">属性</h3>
          <dl class="props-list" v-if="detail.properties && detail.properties.length">
            <div
              v-for="prop in detail.properties"
              :key="prop.key"
              class="prop-row"
            >
              <dt>{{ prop.cn }}</dt>
              <dd>{{ prop.value || '暂无' }}</dd>
            </div>
          </dl>
          <p v-else class="no-data">暂无属性信息</p>
        </div>

        <!-- 推理说明（可折叠） -->
        <div v-if="detail.properties?.find((p: any) => p.key === 'reasoning')?.value" class="reasoning-section">
          <button class="reasoning-toggle" @click="expandReasoning = !expandReasoning">
            {{ expandReasoning ? '▾' : '▸' }} 推理说明
          </button>
          <p v-if="expandReasoning" class="reasoning-text">
            {{ detail.properties.find((p: any) => p.key === 'reasoning')?.value }}
          </p>
        </div>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.left-archive {
  position: relative;
  width: 320px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s ease-out;
  overflow: hidden;
}

.left-archive.collapsed {
  width: 32px;
}

.collapse-handle {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
  width: 20px;
  height: 48px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-right: none;
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
  cursor: pointer;
  font-size: 10px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 5;
  transition: color 0.15s;
}

.collapse-handle:hover {
  color: var(--accent);
}

.archive-content {
  padding: 20px;
  overflow-y: auto;
  height: 100%;
}

/* 骨架 */
.skeleton .sk-line {
  height: 16px;
  background: var(--bg-subtle);
  border-radius: 3px;
  margin-bottom: 12px;
  animation: sk-pulse 1.5s ease-in-out infinite;
}
.sk-line.w-60 { width: 60%; }
.sk-line.w-40 { width: 40%; }
.sk-line.w-80 { width: 80%; }
.sk-line.w-50 { width: 50%; }
.sk-line.w-full { width: 100%; }

@keyframes sk-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

/* 空 */
.empty {
  text-align: center;
  padding-top: 60px;
  color: var(--text-muted);
}
.empty-icon { font-size: 36px; margin-bottom: 12px; opacity: 0.5; }
.empty p { font-size: 14px; }
.empty-sub { font-size: 12px; margin-top: 4px; }

/* 详情 */
.detail-header { margin-bottom: 16px; }
.node-name {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.5;
  margin-bottom: 8px;
}
.node-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.type-tag {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  border: 1px solid;
}
.subtype {
  font-size: 12px;
  color: var(--text-secondary);
}
.degree {
  font-size: 12px;
  color: var(--text-muted);
}

.action-buttons {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.btn-center {
  padding: 6px 12px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent);
  font-size: 13px;
  font-family: inherit;
  color: #fff;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-center:hover {
  background: #9A3E2E;
}
.btn-context {
  flex: 1;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  font-size: 13px;
  font-family: inherit;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-context:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.btn-context:disabled {
  opacity: 0.5;
  cursor: default;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--bg-subtle);
}

.props-list { margin-bottom: 20px; }
.prop-row {
  padding: 6px 0;
  font-size: 13px;
  line-height: 1.7;
  border-bottom: 1px solid var(--bg-subtle);
}
.prop-row:last-child {
  border-bottom: none;
}
.prop-row dt {
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: 2px;
}
.prop-row dd {
  color: var(--text-primary);
  word-break: break-all;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  max-height: 6.8em;
  overflow-y: auto;
}
.no-data {
  font-size: 13px;
  color: var(--text-muted);
  padding: 8px 0;
}

.reasoning-section {
  margin-bottom: 20px;
}
.reasoning-toggle {
  background: none;
  border: none;
  font-size: 13px;
  font-family: inherit;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 0;
}
.reasoning-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  padding: 8px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  margin-top: 6px;
}

/* 档案影像 */
.image-section {
  margin-bottom: 20px;
}

.img-loading,
.img-error,
.img-placeholder-box {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
.img-loading span,
.img-error span,
.img-placeholder-box span {
  font-size: 28px;
  opacity: 0.4;
}
.img-loading p,
.img-error p,
.img-placeholder-box p {
  margin-top: 8px;
}

.img-container {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--bg-canvas);
}

.archive-image {
  display: block;
  width: 100%;
  height: auto;
  max-height: 400px;
  object-fit: contain;
  cursor: zoom-in;
  transition: transform 0.2s;
}
.archive-image:hover {
  opacity: 0.95;
}

.img-caption {
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  border-top: 1px solid var(--bg-subtle);
  background: var(--bg-panel);
}

/* 原档案文本 */
.source-section { margin-bottom: 20px; }
.source-text {
  font-family: "Source Han Serif SC", "Songti SC", "SimSun", serif;
  font-size: 15px;
  line-height: 1.9;
  color: var(--text-primary);
  background: var(--bg-canvas);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
