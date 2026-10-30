import React, { useState } from 'react'
import { Box, Typography, TextField, Button, Card, Chip, Alert, Link } from '@mui/material'
import * as api from '../api'
import { MONO_FONT } from '../theme'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

const Placeholder = ({ children }) => (
  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.disabled', fontSize: '0.875rem', textAlign: 'center', px: 2 }}>{children}</Box>
)

const KindChip = ({ kind }) => (
  <Chip size="small" label={kind === 'attachment' ? '첨부' : '페이지'} color={kind === 'attachment' ? 'success' : 'primary'} variant="filled" sx={{ flexShrink: 0 }} />
)

export default function SearchView() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [passed, setPassed] = useState(true)
  const [searched, setSearched] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [related, setRelated] = useState({})

  const submit = async (e) => {
    e?.preventDefault()
    if (!q.trim() || loading) return
    setLoading(true); setError('')
    try {
      const data = await api.search(q.trim(), 20)
      setResults(data.results); setPassed(data.passed); setSelected(null); setRelated({}); setSearched(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // 왼쪽 목록에서 고르면 오른쪽에 청크 본문과 유사 문서를 보여준다
  const select = async (r) => {
    setSelected(r)
    if (!related[r.document_id]) {
      try {
        const data = await api.getRelated(r.document_id, 5)
        setRelated((prev) => ({ ...prev, [r.document_id]: data.results }))
      } catch { /* 유사 문서 조회 실패는 무시 */ }
    }
  }

  return (
    // 위: 검색어(고정) / 아래: 결과 목록(왼쪽)·선택한 결과 상세(오른쪽) 두 칸이 남은 높이를 쓰고 각자 안에서 스크롤된다
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Box component="form" sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2, flexShrink: 0 }} onSubmit={submit}>
        <TextField fullWidth size="small" value={q} onChange={(e) => setQ(e.target.value)} placeholder="검색어 (답변 생성 없이 청크만 조회)" />
        <Button type="submit" variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} disabled={loading || !q.trim()}>{loading ? '검색 중…' : '검색'}</Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2, flexShrink: 0 }}>{error}</Alert>}
      {!passed && results.length > 0 && <Alert severity="warning" sx={{ mb: 2, flexShrink: 0 }}>리랭커 점수가 하한 미만입니다. 답변 단계에서는 "못 찾음"으로 처리됩니다.</Alert>}

      <Box sx={{ flex: 1, minHeight: 0, display: 'flex', gap: 2 }}>
        {/* 결과 목록 */}
        <Card variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
            검색 결과
            {searched && <Typography component="span" color="text.secondary"> · {results.length}건</Typography>}
          </Typography>
          {results.length > 0
            ? (
              <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 0.5 }}>
                {results.map((r) => {
                  const active = selected?.chunk_id === r.chunk_id
                  return (
                    <Box
                      key={r.chunk_id}
                      onClick={() => select(r)}
                      sx={{
                        p: 1.25, mb: 0.75, borderRadius: 1.5, cursor: 'pointer', border: 1,
                        borderColor: active ? 'primary.main' : 'divider',
                        backgroundColor: active ? 'action.selected' : 'transparent',
                        '&:hover': { backgroundColor: active ? 'action.selected' : 'action.hover' },
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                        <KindChip kind={r.kind} />
                        <Typography noWrap sx={{ fontWeight: 500, minWidth: 0 }}>{r.title}</Typography>
                        <Box sx={{ ml: 'auto', display: 'flex', gap: 1.25, fontFamily: MONO_FONT, fontSize: '0.75rem', flexShrink: 0 }}>
                          {r.rerank_score != null && <span>{r.rerank_score.toFixed(3)}</span>}
                          <span style={{ color: '#71717a' }}>v{r.vector_rank ?? '-'} · k{r.keyword_rank ?? '-'}</span>
                        </Box>
                      </Box>
                      <Typography noWrap sx={{ fontSize: '0.75rem', mt: 0.5, color: 'text.secondary' }}>
                        {r.heading ? `${r.heading} · ` : ''}{r.path} · {fmtDate(r.updated_at)}
                      </Typography>
                    </Box>
                  )
                })}
              </Box>
            )
            : <Placeholder>{searched ? '검색 결과가 없습니다.' : '검색어를 입력하면 결과가 여기에 표시됩니다.'}</Placeholder>}
        </Card>

        {/* 선택한 결과 상세 */}
        <Card variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          {selected
            ? (
              <>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.5, flexShrink: 0 }}>
                  <KindChip kind={selected.kind} />
                  <Typography variant="h6" noWrap sx={{ minWidth: 0 }}>{selected.title}</Typography>
                  <Link href={selected.url} target="_blank" rel="noreferrer" sx={{ ml: 'auto', flexShrink: 0, fontSize: '0.8125rem' }}>열기 ↗</Link>
                </Box>
                <Typography sx={{ fontSize: '0.75rem', mb: 1, color: 'text.secondary', flexShrink: 0 }}>
                  {selected.path}{selected.heading ? ` › ${selected.heading}` : ''} · 수정 {fmtDate(selected.updated_at)}
                </Typography>
                <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 0.5 }}>
                  <Box component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap', fontFamily: MONO_FONT, fontSize: '0.75rem', backgroundColor: 'background.default', border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5 }}>{selected.content}</Box>
                  <Box sx={{ mt: 1.5 }}>
                    <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.04em' }}>유사 문서</Typography>
                    {related[selected.document_id]
                      ? related[selected.document_id].length > 0
                        ? related[selected.document_id].map((d) => (
                          <Box key={d.document_id} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.5, fontSize: '0.8125rem', minWidth: 0 }}>
                            <KindChip kind={d.kind} />
                            <Link href={d.url} target="_blank" rel="noreferrer" noWrap sx={{ minWidth: 0 }}>{d.title}</Link>
                            <Typography color="text.secondary" sx={{ fontSize: '0.75rem', flexShrink: 0 }}>{d.space_key}</Typography>
                            <Typography sx={{ ml: 'auto', fontFamily: MONO_FONT, fontSize: '0.6875rem', color: 'text.secondary', flexShrink: 0 }}>{d.score.toFixed(3)}</Typography>
                          </Box>
                        ))
                        : <Typography sx={{ fontSize: '0.8125rem', color: 'text.disabled' }}>유사 문서가 없습니다.</Typography>
                      : <Typography sx={{ fontSize: '0.8125rem', color: 'text.disabled' }}>불러오는 중…</Typography>}
                  </Box>
                </Box>
              </>
            )
            : (
              <>
                <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>상세</Typography>
                <Placeholder>왼쪽 목록에서 결과를 선택하면 청크 본문과 유사 문서가 여기에 표시됩니다.</Placeholder>
              </>
            )}
        </Card>
      </Box>
    </Box>
  )
}
