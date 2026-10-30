import React, { useState } from 'react'
import * as api from '../api'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

export default function SearchView() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [passed, setPassed] = useState(true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState({})
  const [related, setRelated] = useState({})

  const submit = async (e) => {
    e?.preventDefault()
    if (!q.trim() || loading) return
    setLoading(true); setError('')
    try {
      const data = await api.search(q.trim(), 20)
      setResults(data.results); setPassed(data.passed); setOpen({}); setRelated({})
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const toggle = async (r) => {
    const isOpen = !open[r.chunk_id]
    setOpen((o) => ({ ...o, [r.chunk_id]: !o[r.chunk_id] }))
    if (isOpen && !related[r.document_id]) {
      try {
        const data = await api.getRelated(r.document_id, 5)
        setRelated((prev) => ({ ...prev, [r.document_id]: data.results }))
      } catch { /* 유사 문서 조회 실패는 무시 */ }
    }
  }

  return (
    <div className="search">
      <form className="askbar" onSubmit={submit}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="검색어 (답변 생성 없이 청크만 조회)" />
        <button type="submit" className="btn primary" disabled={loading || !q.trim()}>{loading ? '검색 중…' : '검색'}</button>
      </form>
      {error && <div className="alert error">{error}</div>}
      {!passed && results.length > 0 && <div className="alert warn">리랭커 점수가 하한 미만입니다. 답변 단계에서는 "못 찾음"으로 처리됩니다.</div>}
      <ul className="results">
        {results.map((r) => (
          <li key={r.chunk_id} className="result">
            <div className="result-head" onClick={() => toggle(r)}>
              <span className={`kind ${r.kind}`}>{r.kind === 'attachment' ? '첨부' : '페이지'}</span>
              <span className="title">{r.title}</span>
              {r.heading && <span className="muted"> › {r.heading}</span>}
              <span className="scores">
                {r.rerank_score != null && <span title="리랭크 점수">{r.rerank_score.toFixed(3)}</span>}
                <span className="muted" title="벡터 순위 / 키워드 순위">v{r.vector_rank ?? '-'} · k{r.keyword_rank ?? '-'}</span>
              </span>
            </div>
            <div className="result-meta">
              <span className="muted">{r.path}</span>
              <span className="muted"> · {fmtDate(r.updated_at)}</span>
              <a href={r.url} target="_blank" rel="noreferrer"> 열기 ↗</a>
            </div>
            {open[r.chunk_id] && (
              <>
                <pre className="chunk">{r.content}</pre>
                {related[r.document_id] && related[r.document_id].length > 0 && (
                  <div className="related">
                    <div className="related-title">유사 문서</div>
                    {related[r.document_id].map((d) => (
                      <div key={d.document_id} className="related-item">
                        <span className={`kind ${d.kind}`}>{d.kind === 'attachment' ? '첨부' : '페이지'}</span>
                        <a href={d.url} target="_blank" rel="noreferrer">{d.title}</a>
                        <span className="muted">{d.space_key}</span>
                        <span className="score">{d.score.toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {!loading && results.length === 0 && !error && <div className="empty muted">검색 결과가 여기에 표시됩니다. 행을 누르면 청크 본문과 유사 문서가 펼쳐집니다.</div>}
    </div>
  )
}
