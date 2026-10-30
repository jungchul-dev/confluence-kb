import React, { useEffect, useRef, useState } from 'react'
import { Box, Typography, TextField, Button, Card, Alert, Tooltip } from '@mui/material'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as api from '../api'
import SourceList from '../components/SourceList'

const Placeholder = ({ children }) => (
  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.disabled', fontSize: '0.875rem', textAlign: 'center', px: 2 }}>{children}</Box>
)

// 대화 한 턴. turn = { role: 'user'|'assistant', content, sources?, found?, top_score?, search_query?, latency_ms?, error? }
const Turn = ({ turn, running, selected, onSelect }) => {
  if (turn.role === 'user') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1.5 }}>
        <Box sx={{ maxWidth: '85%', px: 1.75, py: 1.25, borderRadius: 2, backgroundColor: 'primary.main', color: 'primary.contrastText', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{turn.content}</Box>
      </Box>
    )
  }
  return (
    <Box
      onClick={onSelect}
      sx={{
        mb: 2, px: 1.75, py: 1.25, borderRadius: 2, border: 1, cursor: onSelect ? 'pointer' : 'default',
        borderColor: selected ? 'primary.main' : 'divider', backgroundColor: selected ? 'action.selected' : 'background.default',
        color: turn.found === false ? 'text.secondary' : 'text.primary',
      }}
    >
      {turn.search_query && turn.search_query !== turn.question && (
        <Tooltip title="이어지는 질문이라 이전 대화를 반영해 이 문장으로 검색했습니다">
          <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary', mb: 0.5 }}>검색: {turn.search_query}</Typography>
        </Tooltip>
      )}
      <Box sx={{ lineHeight: 1.6, '& > :first-of-type': { mt: 0 }, '& > :last-child': { mb: 0 } }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content || (running ? '…' : ' ')}</ReactMarkdown>
      </Box>
      {turn.error && <Alert severity="error" sx={{ mt: 1 }}>{turn.error}</Alert>}
      <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary', mt: 0.75 }}>
        {running ? '생성 중…' : (turn.latency_ms != null ? `${(turn.latency_ms / 1000).toFixed(1)}s` : '')}
        {turn.sources?.length > 0 && ` · 출처 ${turn.sources.length}건`}
        {turn.found === false && ' · 관련 문서를 찾지 못함'}
      </Typography>
    </Box>
  )
}

export default function AskView() {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState([])          // 대화 전체 (서버에는 이전 턴을 history 로 보낸다)
  const [selected, setSelected] = useState(null)  // 출처를 보여줄 답변 턴의 index (기본: 마지막)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef(null)
  const listRef = useRef(null)

  // 새 조각이 올 때마다 대화 목록을 아래로 붙인다
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
    setSelected(null)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const result = await api.ask(q, {
        history,
        signal: controller.signal,
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

  const reset = () => { abortRef.current?.abort(); setTurns([]); setSelected(null); setError('') }

  const answerTurns = turns.map((t, i) => ({ t, i })).filter(({ t }) => t.role === 'assistant')
  const current = selected != null ? turns[selected] : (answerTurns.length ? answerTurns[answerTurns.length - 1].t : null)
  const hasSources = current?.sources?.length > 0

  return (
    // 위: 질문 입력(고정, 길어지면 안에서 스크롤) / 아래: 대화(왼쪽)·출처(오른쪽) 두 칸이 남은 높이를 모두 쓴다
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Box component="form" sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', mb: 2, flexShrink: 0 }} onSubmit={submit}>
        <TextField
          multiline fullWidth rows={7}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
          placeholder={turns.length ? '이어서 질문하세요. 이전 대화를 참고해 답합니다 (Enter 전송, Shift+Enter 줄바꿈)' : '예) 2026년 ***** 제안에서 선택한 메시지 큐는? (Enter 전송, Shift+Enter 줄바꿈)'}
          size="small"
        />
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0 }}>
          {running
            ? <Button variant="outlined" size="small" sx={{ whiteSpace: 'nowrap' }} onClick={() => abortRef.current?.abort()}>중지</Button>
            : <Button type="submit" variant="contained" size="small" sx={{ whiteSpace: 'nowrap' }} disabled={!question.trim()}>질문</Button>}
          <Button variant="text" size="small" sx={{ whiteSpace: 'nowrap' }} onClick={reset} disabled={!turns.length}>새 대화</Button>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2, flexShrink: 0 }}>{error}</Alert>}

      <Box sx={{ flex: 1, minHeight: 0, display: 'flex', gap: 2 }}>
        {/* 대화 */}
        <Card variant="outlined" sx={{ p: 2, flex: 3, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
            대화
            {turns.length > 0 && <Typography component="span" color="text.secondary"> · {answerTurns.length}턴 (답변을 누르면 그 출처가 오른쪽에 보입니다)</Typography>}
          </Typography>
          {turns.length
            ? (
              <Box ref={listRef} sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 1 }}>
                {turns.map((t, i) => (
                  <Turn
                    key={i}
                    turn={t}
                    running={running && i === turns.length - 1}
                    selected={t.role === 'assistant' && (selected != null ? selected === i : i === turns.length - 1)}
                    onSelect={t.role === 'assistant' ? () => setSelected(i) : undefined}
                  />
                ))}
              </Box>
            )
            : <Placeholder>질문을 입력하면 대화가 여기에 쌓입니다. 이어지는 질문은 이전 대화를 참고합니다.</Placeholder>}
        </Card>

        {/* 출처 */}
        <Card variant="outlined" sx={{ p: 2, flex: 2, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
            {current?.found === false ? '비슷한 문서' : '출처'}
            {current?.top_score != null && <Typography component="span" color="text.secondary"> · 최고 점수 {current.top_score.toFixed(2)}</Typography>}
          </Typography>
          {hasSources
            ? (
              <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 1 }}>
                <SourceList sources={current.sources} />
              </Box>
            )
            : <Placeholder>{running ? '출처를 찾는 중…' : '답변에 사용된 문서가 여기에 표시됩니다.'}</Placeholder>}
        </Card>
      </Box>
    </Box>
  )
}
