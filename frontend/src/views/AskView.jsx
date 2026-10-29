import React, { useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as api from '../api'
import SourceList from '../components/SourceList'

export default function AskView() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [meta, setMeta] = useState(null)
  const [done, setDone] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef(null)

  const submit = async (e) => {
    e?.preventDefault()
    const q = question.trim()
    if (!q || running) return
    setRunning(true); setError(''); setAnswer(''); setMeta(null); setDone(null)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await api.ask(q, {
        signal: controller.signal,
        onMeta: (m) => { setMeta(m); if (m.found === false) setAnswer(m.answer || '') },
        onDelta: (d) => setAnswer((prev) => prev + d),
      })
      setDone(result)
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }

  return (
    <div className="ask">
      <form className="askbar" onSubmit={submit}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
          placeholder="예) 2024년 결제 모듈 개편 제안에서 선택한 메시지 큐는? (Enter 전송, Shift+Enter 줄바꿈)"
          rows={2}
        />
        {running
          ? <button type="button" className="btn" onClick={() => abortRef.current?.abort()}>중지</button>
          : <button type="submit" className="btn primary" disabled={!question.trim()}>질문</button>}
      </form>

      {error && <div className="alert error">{error}</div>}

      {(answer || running) && (
        <section className="panel">
          <div className="panel-title">
            답변
            {running && <span className="muted"> · 생성 중…</span>}
            {done && <span className="muted"> · {(done.latency_ms / 1000).toFixed(1)}s</span>}
          </div>
          <div className={meta?.found === false ? 'answer notfound' : 'answer'}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer || ' '}</ReactMarkdown>
          </div>
        </section>
      )}

      {meta?.sources?.length > 0 && (
        <section className="panel">
          <div className="panel-title">
            {meta.found === false ? '비슷한 문서' : '출처'}
            {meta.top_score != null && <span className="muted"> · 최고 점수 {meta.top_score.toFixed(2)}</span>}
          </div>
          <SourceList sources={meta.sources} />
        </section>
      )}

      {!answer && !running && !error && (
        <div className="empty">
          <p>Confluence 제안서·실행 기록을 근거로 답합니다. 답변의 [n] 은 아래 출처 번호입니다.</p>
          <p className="muted">문서에 없는 내용은 "확인되지 않는다"고 답하고, 관련 문서를 못 찾으면 비슷한 문서만 보여줍니다.</p>
        </div>
      )}
    </div>
  )
}
