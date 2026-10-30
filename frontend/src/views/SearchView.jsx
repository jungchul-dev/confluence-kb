import React, { useState } from 'react'
import { Box, Typography, TextField, Button, Card, Chip, Alert, Link, Collapse } from '@mui/material'
import * as api from '../api'
import { MONO_FONT } from '../theme'

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
    <Box>
      <Box component="form" sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }} onSubmit={submit}>
        <TextField fullWidth size="small" value={q} onChange={(e) => setQ(e.target.value)} placeholder="검색어 (답변 생성 없이 청크만 조회)" />
        <Button type="submit" variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} disabled={loading || !q.trim()}>{loading ? '검색 중…' : '검색'}</Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {!passed && results.length > 0 && <Alert severity="warning" sx={{ mb: 2 }}>리랭커 점수가 하한 미만입니다. 답변 단계에서는 "못 찾음"으로 처리됩니다.</Alert>}

      {results.map((r) => (
        <Card key={r.chunk_id} variant="outlined" sx={{ p: 1.5, mb: 1, cursor: 'pointer', '&:hover': { borderColor: 'borderStrong' } }} onClick={() => toggle(r)}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
            <Chip size="small" label={r.kind === 'attachment' ? '첨부' : '페이지'} color={r.kind === 'attachment' ? 'success' : 'primary'} variant="filled" />
            <Typography sx={{ fontWeight: 500 }}>{r.title}</Typography>
            {r.heading && <Typography color="text.secondary"> › {r.heading}</Typography>}
            <Box sx={{ ml: 'auto', display: 'flex', gap: 1.25, fontFamily: MONO_FONT, fontSize: '0.75rem' }}>
              {r.rerank_score != null && <span>{r.rerank_score.toFixed(3)}</span>}
              <span style={{ color: '#71717a' }}>v{r.vector_rank ?? '-'} · k{r.keyword_rank ?? '-'}</span>
            </Box>
          </Box>
          <Box sx={{ fontSize: '0.75rem', mt: 0.5, color: 'text.secondary' }}>
            {r.path} · {fmtDate(r.updated_at)} <Link href={r.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>열기 ↗</Link>
          </Box>
          <Collapse in={!!open[r.chunk_id]}>
            <Box sx={{ mt: 1 }}>
              <Box component="pre" sx={{ whiteSpace: 'pre-wrap', fontFamily: MONO_FONT, fontSize: '0.75rem', backgroundColor: 'background.default', border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5, maxHeight: 320, overflow: 'auto' }}>{r.content}</Box>
              {related[r.document_id]?.length > 0 && (
                <Box sx={{ mt: 1, ml: 2.5, p: 1.5, backgroundColor: 'background.default', border: 1, borderColor: 'divider', borderRadius: 1 }}>
                  <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.04em' }}>유사 문서</Typography>
                  {related[r.document_id].map((d) => (
                    <Box key={d.document_id} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.5, fontSize: '0.8125rem' }}>
                      <Chip size="small" label={d.kind === 'attachment' ? '첨부' : '페이지'} color={d.kind === 'attachment' ? 'success' : 'primary'} variant="filled" />
                      <Link href={d.url} target="_blank" rel="noreferrer">{d.title}</Link>
                      <Typography color="text.secondary" sx={{ fontSize: '0.75rem' }}>{d.space_key}</Typography>
                      <Typography sx={{ ml: 'auto', fontFamily: MONO_FONT, fontSize: '0.6875rem', color: 'text.secondary' }}>{d.score.toFixed(3)}</Typography>
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
          </Collapse>
        </Card>
      ))}

      {!loading && results.length === 0 && !error && (
        <Box sx={{ textAlign: 'center', py: 5, color: 'text.secondary' }}>검색 결과가 여기에 표시됩니다. 행을 누르면 청크 본문과 유사 문서가 펼쳐집니다.</Box>
      )}
    </Box>
  )
}
