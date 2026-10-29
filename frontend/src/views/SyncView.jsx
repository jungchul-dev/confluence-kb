import React, { useCallback, useEffect, useState } from 'react'
import * as api from '../api'

const fmt = (iso) => (iso ? new Date(iso).toLocaleString('ko-KR') : '-')

export default function SyncView() {
  const [status, setStatus] = useState(null)
  const [errors, setErrors] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([api.syncStatus(), api.syncErrors()])
      setStatus(s); setErrors(e); setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  const run = async (mode) => {
    setBusy(true)
    try {
      await api.runSync(mode)
      setTimeout(load, 1000)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sync">
      <div className="toolbar">
        <button className="btn" onClick={() => run('incremental')} disabled={busy || status?.running}>증분 동기화</button>
        <button className="btn" onClick={() => run('full')} disabled={busy || status?.running}>전체 동기화</button>
        {status?.running && <span className="muted">실행 중…</span>}
        <button className="btn ghost" onClick={load}>새로고침</button>
      </div>
      {error && <div className="alert error">{error}</div>}

      <section className="panel">
        <div className="panel-title">공간</div>
        <table>
          <thead><tr><th>공간</th><th>문서</th><th>페이지</th><th>오류</th><th>마지막 동기화</th></tr></thead>
          <tbody>
            {(status?.spaces || []).map((s) => (
              <tr key={s.space_key}>
                <td><code>{s.space_key}</code></td><td>{s.documents}</td><td>{s.pages}</td>
                <td className={s.errors ? 'bad' : ''}>{s.errors}</td><td>{fmt(s.last_synced_at)}</td>
              </tr>
            ))}
            {status && status.spaces.length === 0 && <tr><td colSpan={5} className="muted">CONFLUENCE_SPACES 가 비어 있습니다.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <div className="panel-title">최근 실행</div>
        <table>
          <thead><tr><th>시작</th><th>공간</th><th>모드</th><th>상태</th><th>조회</th><th>색인</th><th>첨부</th><th>삭제</th><th>오류</th></tr></thead>
          <tbody>
            {(status?.runs || []).map((r) => (
              <tr key={r.id}>
                <td>{fmt(r.started_at)}</td><td><code>{r.space_key}</code></td><td>{r.mode}</td>
                <td className={r.status === 'failed' ? 'bad' : r.status === 'success' ? 'good' : ''}>{r.status}{r.message ? ` · ${r.message}` : ''}</td>
                <td>{r.pages_seen}</td><td>{r.pages_indexed}</td><td>{r.attachments_indexed}</td><td>{r.pages_deleted}</td><td className={r.errors ? 'bad' : ''}>{r.errors}</td>
              </tr>
            ))}
            {status && status.runs.length === 0 && <tr><td colSpan={9} className="muted">아직 실행 기록이 없습니다.</td></tr>}
          </tbody>
        </table>
      </section>

      {errors.length > 0 && (
        <section className="panel">
          <div className="panel-title">페이지 오류 ({errors.length})</div>
          <table>
            <thead><tr><th>페이지 id</th><th>공간</th><th>버전</th><th>시각</th><th>오류</th></tr></thead>
            <tbody>
              {errors.map((e) => (
                <tr key={e.page_id}><td><code>{e.page_id}</code></td><td>{e.space_key}</td><td>{e.version}</td><td>{fmt(e.synced_at)}</td><td className="bad">{e.error}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
