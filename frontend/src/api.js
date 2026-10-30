// API 클라이언트 — 개발 중에는 vite 프록시가 /api 를 8001 로 넘긴다.
// 사용자 식별 헤더는 운영에서 SSO 프록시가 넣는다. 개발용으로 localStorage 의 userId / userGroups 를 보낸다.
const BASE = '/api/v1'

const headers = () => {
  const h = { 'Content-Type': 'application/json' }
  try {
    const uid = localStorage.getItem('userId')
    const groups = localStorage.getItem('userGroups')
    if (uid) h['X-User-Id'] = uid
    if (groups) h['X-User-Groups'] = groups
  } catch { /* 저장소 접근 불가 시 무시 */ }
  return h
}

const request = async (path, { method = 'GET', body } = {}) => {
  const res = await fetch(`${BASE}${path}`, { method, headers: headers(), body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `${res.status} ${res.statusText}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export const health = () => request('/health')
export const search = (q, k = 10) => request(`/search?q=${encodeURIComponent(q)}&k=${k}`)
export const getDocument = (pageId, attachmentId) =>
  request(`/documents/${pageId}${attachmentId ? `?attachment_id=${attachmentId}` : ''}`)
export const getRelated = (documentId, k = 5) =>
  request(`/related-documents?document_id=${encodeURIComponent(documentId)}&k=${k}`)
export const getClusters = (k = 0) =>
  request(`/admin/clusters${k > 0 ? `?k=${k}` : ''}`)
export const syncStatus = () => request('/admin/sync/status')
export const syncErrors = () => request('/admin/sync/errors')
export const runSync = (mode, spaces) => request('/admin/sync/run', { method: 'POST', body: { mode, spaces: spaces || null } })

// 질문 — SSE 스트리밍. onMeta(출처), onDelta(답변 조각), 완료 시 { query_id, latency_ms } 를 돌려준다.
export const ask = async (question, { onMeta, onDelta, signal } = {}) => {
  const res = await fetch(`${BASE}/ask?stream=true`, { method: 'POST', headers: headers(), body: JSON.stringify({ question }), signal })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `${res.status} ${res.statusText}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let done = null
  for (;;) {
    const { done: finished, value } = await reader.read()
    if (finished) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      const payload = JSON.parse(data)
      if (event === 'meta') onMeta?.(payload)
      else if (event === 'delta') onDelta?.(payload)
      else if (event === 'done') done = payload
      else if (event === 'error') throw new Error(payload.detail || '답변 생성 실패')
    }
  }
  return done
}
