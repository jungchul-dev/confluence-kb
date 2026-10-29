import React from 'react'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

export default function SourceList({ sources }) {
  return (
    <ol className="sources">
      {sources.map((s) => (
        <li key={s.document_id}>
          <span className="idx">[{s.index}]</span>
          <a href={s.url} target="_blank" rel="noreferrer" className="title">{s.title}</a>
          <span className={`kind ${s.kind}`}>{s.kind === 'attachment' ? '첨부' : '페이지'}</span>
          <div className="meta muted">{s.path} · 수정 {fmtDate(s.updated_at)} · 점수 {s.score.toFixed(2)}</div>
        </li>
      ))}
    </ol>
  )
}
