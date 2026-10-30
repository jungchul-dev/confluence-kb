import React, { useCallback, useEffect, useState } from 'react'
import * as api from '../api'

const CLUSTER_COLORS = ['#2563eb', '#16a34a', '#dc2626', '#9333ea', '#ea580c', '#0891b2', '#ca8a04', '#be185d']

export default function AnalyticsView() {
  const [clusters, setClusters] = useState([])
  const [totalDocs, setTotalDocs] = useState(0)
  const [k, setK] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const data = await api.getClusters(k)
      setClusters(data.clusters); setTotalDocs(data.total_documents); setK(data.k)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [k])

  useEffect(() => { load() }, [load])

  return (
    <div className="analytics">
      <div className="toolbar">
        <label className="muted">클러스터 수 </label>
        <input type="number" min={0} max={50} value={k} onChange={(e) => setK(Number(e.target.value))} style={{ width: 60 }} />
        <span className="muted" style={{ fontSize: 12 }}>0 = 자동</span>
        <button className="btn primary" onClick={load} disabled={loading}>{loading ? '분석 중…' : '분석'}</button>
      </div>
      {error && <div className="alert error">{error}</div>}

      <div className="muted" style={{ marginBottom: 12 }}>
        전체 문서 {totalDocs}개 · 클러스터 {clusters.length}개
      </div>

      {clusters.map((c, i) => (
        <div key={c.cluster_id} className="cluster">
          <div className="cluster-head">
            <span className="cluster-badge" style={{ background: CLUSTER_COLORS[i % CLUSTER_COLORS.length] }}>
              클러스터 {c.cluster_id}
            </span>
            <span className="cluster-count">{c.doc_count}개 문서</span>
          </div>
          <ul className="cluster-docs">
            {c.representative_docs.map((d) => (
              <li key={d.document_id}>
                <span className={`kind ${d.kind}`}>{d.kind === 'attachment' ? '첨부' : '페이지'}</span>
                <a href={d.url} target="_blank" rel="noreferrer">{d.title}</a>
                <span className="muted" style={{ marginLeft: 8 }}>{d.space_key}</span>
              </li>
            ))}
          </ul>
          {c.all_titles.length > c.representative_docs.length && (
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              외 {c.all_titles.length - c.representative_docs.length}개 문서
            </div>
          )}
        </div>
      ))}

      {!loading && clusters.length === 0 && !error && <div className="empty muted">문서가 2개 이상일 때 클러스터링 결과가 표시됩니다.</div>}
    </div>
  )
}
