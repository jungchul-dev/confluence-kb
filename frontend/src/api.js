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
export const getSpaces = () => request('/admin/spaces')
export const search = (q, k = 10, spaceKeys = []) =>
  request(`/search?q=${encodeURIComponent(q)}&k=${k}${spaceKeys.length ? `&space_key=${encodeURIComponent(spaceKeys.join(','))}` : ''}`)
export const getDocument = (pageId, attachmentId) =>
  request(`/documents/${pageId}${attachmentId ? `?attachment_id=${attachmentId}` : ''}`)
export const getRelated = (documentId, k = 5) =>
  request(`/related-documents?document_id=${encodeURIComponent(documentId)}&k=${k}`)
export const getClusters = (k = 0, spaceKeys = []) =>
  request(`/admin/clusters${k > 0 ? `?k=${k}` : ''}${spaceKeys.length ? `${k > 0 ? '&' : '?'}space_key=${encodeURIComponent(spaceKeys.join(','))}` : ''}`)
export const syncStatus = () => request('/admin/sync/status')
export const syncErrors = () => request('/admin/sync/errors')
export const runSync = (mode, spaces) => request('/admin/sync/run', { method: 'POST', body: { mode, spaces: spaces || null } })

// 질문 — SSE 스트리밍. history 는 이전 대화 [{ role: 'user'|'assistant', content }] (서버가 ASK_HISTORY_TURNS 턴으로 자른다).
// onMeta(출처·검색 문장), onDelta(답변 조각), 완료 시 { query_id, latency_ms } 를 돌려준다.
export const ask = async (question, { history = [], onMeta, onDelta, signal, spaceKeys = [] } = {}) => {
  const res = await fetch(`${BASE}/ask?stream=true`, { method: 'POST', headers: headers(), body: JSON.stringify({ question, history, space_key: spaceKeys.length ? spaceKeys : null }), signal })
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

// ───────── 자료 작성 ─────────
// 파일은 base64 JSON 으로 보낸다 (서버 상한 20MB)
export const fileToBase64 = (file) => new Promise((resolve, reject) => {
  const r = new FileReader()
  r.onload = () => resolve(String(r.result).split(',', 2)[1] || '')
  r.onerror = () => reject(new Error('파일을 읽지 못했습니다.'))
  r.readAsDataURL(file)
})

export const listDrafts = () => request('/drafts')
export const getDraft = (id) => request(`/drafts/${id}`)
export const createDraft = (name, overview, docFormat) => request('/drafts', { method: 'POST', body: { name, overview, doc_format: docFormat } })
export const updateDraft = (id, body) => request(`/drafts/${id}`, { method: 'PUT', body })
export const deleteDraft = (id) => request(`/drafts/${id}`, { method: 'DELETE' })

// 목차 — 템플릿이 없으면 작성 개요 · 요구사항으로 제안받고 직접 고친다
export const proposeOutline = (id, replace = false) => request(`/drafts/${id}/outline`, { method: 'POST', body: { replace } })
export const addSection = (id, title) => request(`/drafts/${id}/sections`, { method: 'POST', body: { title } })
export const updateDraftSection = (id, sectionId, body) => request(`/drafts/${id}/sections/${sectionId}`, { method: 'PUT', body })
export const deleteSection = (id, sectionId) => request(`/drafts/${id}/sections/${sectionId}`, { method: 'DELETE' })
export const reorderSections = (id, ids) => request(`/drafts/${id}/sections-order`, { method: 'PUT', body: { ids } })

// 템플릿(1개) · 참고 문서(최대 5개) — 목차를 만들기 전에 올린다. 올리면 저장만 하고 목차 제안 · 생성 때 쓴다
export const uploadTemplate = async (id, file) => request(`/drafts/${id}/template`, { method: 'POST', body: { file_name: file.name, data_base64: await fileToBase64(file) } })
export const removeTemplate = (id) => request(`/drafts/${id}/template`, { method: 'DELETE' })
export const uploadReference = async (id, file) => request(`/drafts/${id}/references`, { method: 'POST', body: { file_name: file.name, data_base64: await fileToBase64(file) } })
export const removeReference = (id, referenceId) => request(`/drafts/${id}/references/${referenceId}`, { method: 'DELETE' })

export const uploadRequirementFile = async (id, file) => request(`/drafts/${id}/files`, { method: 'POST', body: { file_name: file.name, data_base64: await fileToBase64(file) } })
export const deleteRequirementFile = (id, fileId) => request(`/drafts/${id}/files/${fileId}`, { method: 'DELETE' })
export const addRequirement = (id, content, sectionId) => request(`/drafts/${id}/requirements`, { method: 'POST', body: { content, section_id: sectionId || null } })
export const updateRequirement = (id, reqId, body) => request(`/drafts/${id}/requirements/${reqId}`, { method: 'PUT', body })
export const deleteRequirement = (id, reqId) => request(`/drafts/${id}/requirements/${reqId}`, { method: 'DELETE' })

// spaceKeys: 위쪽에서 고른 공간 (비우면 전체)
export const collectSources = (id, sectionId, spaceKeys = []) => request(`/drafts/${id}/collect`, { method: 'POST', body: { section_id: sectionId || null, space_keys: spaceKeys } })
export const listSources = (id, sectionId) => request(`/drafts/${id}/sections/${sectionId}/sources`)
export const updateSource = (id, sourceId, body) => request(`/drafts/${id}/sources/${sourceId}`, { method: 'PATCH', body })
export const deleteSource = (id, sourceId) => request(`/drafts/${id}/sources/${sourceId}`, { method: 'DELETE' })
export const generateSection = (id, sectionId) => request(`/drafts/${id}/sections/${sectionId}/generate`, { method: 'POST' })

// 내보내기 — 파일을 받아 바로 내려받기
export const exportDraft = async (id, fallbackName) => {
  const res = await fetch(`${BASE}/drafts/${id}/export`, { headers: headers() })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `${res.status} ${res.statusText}`)
  }
  const cd = res.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename\*=UTF-8''([^;]+)/)
  const name = m ? decodeURIComponent(m[1]) : `${fallbackName}.docx`
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
