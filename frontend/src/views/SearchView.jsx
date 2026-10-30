import React, { useState } from 'react'
import { Box, Typography, TextField, Button, Card, Chip, Alert, Link, Tooltip } from '@mui/material'
import * as api from '../api'
import { MONO_FONT } from '../theme'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

const Placeholder = ({ children }) => (
  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.disabled', fontSize: '0.875rem', textAlign: 'center', px: 2 }}>{children}</Box>
)

const KindChip = ({ kind }) => (
  <Chip size="small" label={kind === 'attachment' ? '첨부' : '페이지'} color={kind === 'attachment' ? 'success' : 'primary'} variant="filled" sx={{ flexShrink: 0 }} />
)

// 관련도: 리랭커가 none 이면 RRF 를 1위=1.0 으로 정규화한 값, 리랭커가 있으면 리랭커 점수. 0~1 을 % 막대로 보여준다
const RelevanceBar = ({ score }) => {
  const pct = score == null ? null : Math.max(0, Math.min(100, Math.round(score * 100)))
  return (
    <Tooltip title={score == null ? '점수 없음' : `관련도 ${score.toFixed(3)} (리랭커 점수, 리랭커가 없으면 RRF 정규화 점수)`}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexShrink: 0 }}>
        <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>관련도</Typography>
        <Box sx={{ width: 90, height: 6, borderRadius: 3, backgroundColor: 'action.hover', overflow: 'hidden' }}>
          <Box sx={{ width: `${pct ?? 0}%`, height: '100%', backgroundColor: pct == null ? 'transparent' : pct >= 70 ? 'success.main' : pct >= 40 ? 'warning.main' : 'text.disabled' }} />
        </Box>
        <Typography sx={{ fontSize: '0.75rem', fontFamily: MONO_FONT, width: 36, textAlign: 'right' }}>{pct == null ? '-' : `${pct}%`}</Typography>
      </Box>
    </Tooltip>
  )
}

// 순위 배지: 양쪽 검색에 모두 걸린 결과는 진한 색, 한쪽만이면 회색, 안 걸린 쪽은 '없음'
const RankBadge = ({ label, rank, both, tip }) => (
  <Tooltip title={rank == null ? `${label} 검색 상위 후보에 없음` : `${tip} — ${rank}위`}>
    <Chip
      size="small"
      variant={rank == null ? 'outlined' : 'filled'}
      color={rank == null ? 'default' : both ? 'primary' : 'default'}
      label={rank == null ? `${label} 없음` : `${label} ${rank}위`}
      sx={{ fontSize: '0.75rem', height: 22, flexShrink: 0, ...(rank == null ? { color: 'text.disabled', borderStyle: 'dashed' } : {}) }}
    />
  </Tooltip>
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
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.75, minWidth: 0 }}>
                        <RelevanceBar score={r.rerank_score} />
                        <RankBadge label="의미" rank={r.vector_rank} both={r.vector_rank != null && r.keyword_rank != null} tip="임베딩(벡터) 검색 순위. 검색어와 뜻이 비슷한 순서" />
                        <RankBadge label="키워드" rank={r.keyword_rank} both={r.vector_rank != null && r.keyword_rank != null} tip="키워드(형태소) 검색 순위. 검색어 단어가 실제로 들어 있는 순서" />
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
                  <Link href={selected.url} target="_blank" rel="noreferrer" sx={{ ml: 'auto', flexShrink: 0, fontSize: '0.8125rem' }}>열기</Link>
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
                          // 검색 결과 목록과 같은 카드 형태: 종류 칩 + 제목 + 유사도, 아래 줄에 경로 · 공간
                          <Box
                            key={d.document_id}
                            component="a"
                            href={d.url}
                            target="_blank"
                            rel="noreferrer"
                            sx={{
                              display: 'block', p: 1.25, mb: 0.75, borderRadius: 1.5, border: 1, borderColor: 'divider',
                              color: 'inherit', textDecoration: 'none', cursor: 'pointer',
                              '&:hover': { backgroundColor: 'action.hover', borderColor: 'borderStrong' },
                            }}
                          >
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                              <KindChip kind={d.kind} />
                              <Typography noWrap sx={{ fontWeight: 500, minWidth: 0 }}>{d.title}</Typography>
                              <Tooltip title={`코사인 유사도 ${d.score.toFixed(3)}`}>
                                <Typography sx={{ ml: 'auto', fontFamily: MONO_FONT, fontSize: '0.75rem', color: 'text.secondary', flexShrink: 0 }}>유사도 {Math.round(d.score * 100)}%</Typography>
                              </Tooltip>
                            </Box>
                            <Typography noWrap sx={{ fontSize: '0.75rem', mt: 0.5, color: 'text.secondary' }}>
                              {d.path}{d.space_key ? ` · ${d.space_key}` : ''}{d.updated_at ? ` · ${fmtDate(d.updated_at)}` : ''}
                            </Typography>
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
