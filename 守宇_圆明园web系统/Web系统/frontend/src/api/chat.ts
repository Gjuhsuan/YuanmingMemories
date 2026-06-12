/**
 * SSE 流式封装 —— POST + ReadableStream 解析。
 * 支持 SimpleRAG (/api/chat) 和 GraphRAG (/api/chat/graphrag)。
 */
export interface SSEEvent {
  event: string
  data: any
}

function parseSSEStream(response: Response): ReadableStreamDefaultReader | null {
  return response.body?.getReader() || null
}

async function* readSSE(response: Response): AsyncGenerator<SSEEvent> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('不支持流式响应')

  const decoder = new TextDecoder()
  let buffer = ''

  function* parseBuffer(chunk: string): Generator<SSEEvent> {
    buffer += chunk
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const jsonStr = line.slice(6).trim()
        if (!jsonStr) continue
        try {
          const data = JSON.parse(jsonStr)
          yield { event: currentEvent, data }
          currentEvent = ''
        } catch (e) {
          console.warn('[SSE] JSON parse failed:', (e as Error).message)
        }
      }
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        if (buffer.trim()) {
          const finalBlock = buffer + '\n'
          buffer = ''
          yield* parseBuffer(finalBlock)
        }
        break
      }
      const chunk = decoder.decode(value, { stream: true })
      yield* parseBuffer(chunk)
    }
  } finally {
    reader.releaseLock()
  }
}

// ── SimpleRAG ──
export async function* streamChat(
  body: Record<string, any>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: { message: '请求失败' } }))
    throw new Error(err?.error?.message || `HTTP ${response.status}`)
  }
  yield* readSSE(response)
}

// ── GraphRAG 深度检索 ──
export async function* streamGraphRAG(
  body: Record<string, any>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/api/chat/graphrag', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: { message: '请求失败' } }))
    throw new Error(err?.error?.message || `HTTP ${response.status}`)
  }
  yield* readSSE(response)
}
