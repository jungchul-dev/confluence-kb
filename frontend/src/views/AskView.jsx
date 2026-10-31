import React, { useEffect, useRef, useState } from 'react'
import { Box, Typography, TextField, Button, Card, Alert, Tooltip, CircularProgress, IconButton } from '@mui/material'
import { KeyboardArrowDown as DownIcon, KeyboardArrowUp as UpIcon } from '@mui/icons-material'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as api from '../api'
import SourceList from '../components/SourceList'
import { FONT_SIZES } from '../theme'

const Placeholder = ({ children }) => (
  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.disabled', fontSize: FONT_SIZES.md, textAlign: 'center', px: 2 }}>{children}</Box>
)

const citedOf = (turn, running) => {
  if (!turn?.content || running) return null
  const found = new Set()
  for (const m of turn.content.matchAll(/\[(\d+)\]/g)) found.add(Number(m[1]))
  return found.size ? found : null
}

const Turn = ({ turn, running, collapsed, onToggle }) => {
  if (turn.role === 'user') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1.5 }}>
        <Box sx={{ maxWidth: '85%', px: 1.5, py: 0.75, borderRadius: 2, backgroundColor: 'primary.main', color: 'primary.contrastText', whiteSpace: 'pre-wrap', lineHeight: 1.6, fontSize: FONT_SIZES.lg }}>{turn.content}</Box>
      </Box>
    )
  }
  const showSources = !running && turn.sources?.length > 0 && !collapsed
  return (
    <Box sx={{ position: 'relative', mb: 2, px: 1.5, py: 1, borderRadius: 2, border: 1, borderColor: 'divider', backgroundColor: '#fff', color: turn.found === false ? 'text.secondary' : 'text.primary' }}>
      {turn.content && !running && (
        <IconButton size="small" onClick={(e) => { e.stopPropagation(); onToggle() }} sx={{ position: 'absolute', top: 2, right: 2, p: 0.5 }}>
          {collapsed ? <DownIcon fontSize="medium" /> : <UpIcon fontSize="medium" />}
        </IconButton>
      )}
      {turn.search_query && turn.search_query !== turn.question && (
        <Tooltip title="이어지는 질문이라 이전 대화를 반영해 이 문장으로 검색했습니다">
          <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary', mb: 0.5 }}>검색: {turn.search_query}</Typography>
        </Tooltip>
      )}
      {!collapsed && turn.content
        ? (
          <Box sx={{ lineHeight: 1.7, fontSize: FONT_SIZES.lg, '& > :first-of-type': { mt: 0 }, '& > :last-child': { mb: 0 } }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
          </Box>
        )
        : !collapsed && running && <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: 'text.secondary' }}><CircularProgress size={14} /><Typography>생성 중</Typography></Box>}
      {collapsed && turn.content && (
        <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', pr: 3 }}>
          {turn.content.replace(/[#*`_\[\]]/g, '').slice(0, 100)}
        </Typography>
      )}
      {turn.error && <Alert severity="error" sx={{ mt: 1 }}>{turn.error}</Alert>}
      {(!running || turn.content) && (
        <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary', mt: 0.75 }}>
          {running ? <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}><CircularProgress size={12} />생성 중</Box> : (turn.latency_ms != null ? `${(turn.latency_ms / 1000).toFixed(1)}s` : '')}
          {!running && turn.sources?.length > 0 && ` · 출처 ${turn.sources.length}건`}
          {turn.found === false && ' · 관련 문서를 찾지 못함'}
        </Typography>
      )}
      {showSources && (
        <Box sx={{ mt: 1, pt: 1.25, borderTop: 1, borderColor: 'divider' }}>
          <Typography sx={{ fontWeight: 600, color: 'text.secondary', mb: 0.5, fontSize: FONT_SIZES.sm, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {turn.found === false ? '비슷한 문서' : '출처'}
            {turn.top_score != null && <Typography component="span" sx={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0, ml: 0.5, color: 'text.disabled' }}>· 최고 점수 {turn.top_score.toFixed(2)}</Typography>}
          </Typography>
          <SourceList sources={turn.sources} cited={citedOf(turn, running)} />
        </Box>
      )}
    </Box>
  )
}

export default function AskView({ space }) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState(new Set())
  const abortRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => { abortRef.current?.abort(); setTurns([]); setError(''); setCollapsed(new Set()) }, [space])

  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns])

  const updateLast = (patch) => setTurns((prev) => {
    const next = prev.slice()
    const i = next.length - 1
    next[i] = typeof patch === 'function' ? patch(next[i]) : { ...next[i], ...patch }
    return next
  })

  const submit = async (e) => {
    e?.preventDefault()
    const q = question.trim()
    if (!q || running) return
    const history = turns.filter((t) => !t.error).map((t) => ({ role: t.role, content: t.content }))
    setRunning(true); setError(''); setQuestion('')
    setTurns((prev) => [...prev, { role: 'user', content: q }, { role: 'assistant', content: '', question: q }])
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await api.ask(q, {
        history,
        signal: controller.signal,
        spaceKeys: space,
        onMeta: (m) => updateLast((t) => ({ ...t, sources: m.sources, found: m.found, top_score: m.top_score, search_query: m.search_query, content: m.found === false ? (m.answer || '') : t.content })),
        onDelta: (d) => updateLast((t) => ({ ...t, content: t.content + d })),
      })
      updateLast({ latency_ms: result?.latency_ms, query_id: result?.query_id })
    } catch (err) {
      if (err.name === 'AbortError') updateLast({ latency_ms: null })
      else updateLast({ error: err.message })
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }

  const reset = () => { abortRef.current?.abort(); setTurns([]); setError(''); setCollapsed(new Set()) }

  const toggleCollapse = (i) => setCollapsed((prev) => {
    const next = new Set(prev)
    if (next.has(i)) next.delete(i); else next.add(i)
    return next
  })

  const answerCount = turns.filter((t) => t.role === 'assistant').length

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {error && <Alert severity="error" sx={{ mb: 2, flexShrink: 0 }}>{error}</Alert>}

      <Card variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {turns.length
          ? (
            <Box ref={listRef} sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 1 }}>
              {turns.map((t, i) => (
                <Turn
                  key={i}
                  turn={t}
                  running={running && i === turns.length - 1}
                  collapsed={collapsed.has(i)}
                  onToggle={() => toggleCollapse(i)}
                />
              ))}
            </Box>
          )
          : <Placeholder>질문을 입력하면 대화가 여기에 쌓입니다. 이어지는 질문은 이전 대화를 참고합니다.</Placeholder>}
      </Card>

      <Box component="form" sx={{ position: 'relative', mt: 2, flexShrink: 0 }} onSubmit={submit}>
        <TextField
          multiline fullWidth rows={4}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
          placeholder={turns.length ? '이어서 질문하세요. 이전 대화를 참고해 답합니다 (Enter 전송, Shift+Enter 줄바꿈)' : '예) 2026년 ***** 제안에서 선택한 메시지 큐는? (Enter 전송, Shift+Enter 줄바꿈)'}
          size="small"
          sx={{ '& .MuiInputBase-root': { pb: 6 } }}
        />
        <Box sx={{ position: 'absolute', left: 10, bottom: 10 }}>
          {turns.length > 0 && <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary' }}>{answerCount}턴</Typography>}
        </Box>
        <Box sx={{ position: 'absolute', right: 10, bottom: 10, display: 'flex', gap: 1 }}>
          <Button variant="contained" color="inherit" size="small" sx={{ whiteSpace: 'nowrap', backgroundColor: 'background.default', color: 'text.primary', border: 1, borderColor: 'divider', '&:hover': { backgroundColor: 'action.hover' } }} onClick={reset} disabled={!turns.length}>새 대화</Button>
          {running
            ? <Button variant="contained" color="inherit" size="small" sx={{ whiteSpace: 'nowrap' }} onClick={() => abortRef.current?.abort()}>중지</Button>
            : <Button type="submit" variant="contained" size="small" sx={{ whiteSpace: 'nowrap' }} disabled={!question.trim()}>질문</Button>}
        </Box>
      </Box>
    </Box>
  )
}
