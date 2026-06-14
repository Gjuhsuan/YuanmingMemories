/**
 * Axios 封装 + 图谱类端点函数。
 */
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// 错误拦截
http.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.error?.message || err.message || '请求失败'
    console.error('[API]', msg)
    return Promise.reject(err)
  },
)

// ── 图谱域 ──
export function fetchMeta() {
  return http.get('/meta').then((r) => r.data)
}

export function fetchGraph(params: Record<string, any> = {}) {
  return http.get('/graph', { params }).then((r) => r.data)
}

export function fetchNodeDetail(id: string) {
  return http.get(`/node/${encodeURIComponent(id)}`).then((r) => r.data)
}

export function fetchNodeNeighbors(id: string, limit = 50) {
  return http.get(`/node/${encodeURIComponent(id)}/neighbors`, { params: { limit } }).then((r) => r.data)
}

export function searchNodes(q: string, types = '', limit = 20) {
  return http.get('/search', { params: { q, types, limit } }).then((r) => r.data)
}

export function executeCypher(query: string) {
  return http.post('/cypher', { query }).then((r) => r.data)
}

export function fetchDashboard() {
  return http.get('/dashboard').then((r) => r.data)
}

export function fetchPreload() {
  return http.get('/preload').then((r) => r.data)
}

// ── Chat 域 ──
export function chatRetrieve(body: Record<string, any>) {
  return http.post('/chat/retrieve', body).then((r) => r.data)
}

export function getSession(sessionId: string) {
  return http.get(`/chat/sessions/${sessionId}`).then((r) => r.data)
}

export function deleteSession(sessionId: string) {
  return http.delete(`/chat/sessions/${sessionId}`).then((r) => r.data)
}

export { http }
