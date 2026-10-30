import React, { useRef, useState } from 'react'
import { Box, Typography, TextField, Button, Card, Alert } from '@mui/material'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as api from '../api'
import SourceList from '../components/SourceList'

const Placeholder = ({ children }) => (
  <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.disabled', fontSize: '0.875rem', textAlign: 'center', px: 2 }}>{children}</Box>
)

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

  const hasSources = meta?.sources?.length > 0

  return (
    // 위: 질문 입력(고정) / 아래: 답변(왼쪽)·출처(오른쪽) 두 칸이 남은 높이를 모두 쓰고 각자 안에서 스크롤된다
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Box component="form" sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', mb: 2, flexShrink: 0 }} onSubmit={submit}>
        <TextField
          multiline fullWidth minRows={4}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e) }}
          placeholder="예) 2026년 ***** 제안에서 선택한 메시지 큐는? (Enter 전송, Shift+Enter 줄바꿈)"
          size="small"
        />
        {running
          ? <Button variant="outlined" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} onClick={() => abortRef.current?.abort()}>중지</Button>
          : <Button type="submit" variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} disabled={!question.trim()}>질문</Button>}
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2, flexShrink: 0 }}>{error}</Alert>}

      <Box sx={{ flex: 1, minHeight: 0, display: 'flex', gap: 2 }}>
        {/* 답변 */}
        <Card variant="outlined" sx={{ p: 2, flex: 3, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
            답변
            {running && <Typography component="span" color="text.secondary"> · 생성 중…</Typography>}
            {done && <Typography component="span" color="text.secondary"> · {(done.latency_ms / 1000).toFixed(1)}s</Typography>}
          </Typography>
          {(answer || running)
            ? (
              <Box sx={{ flex: 1, lineHeight: 1.6, overflow: 'auto', minHeight: 0, pr: 1, color: meta?.found === false ? 'text.secondary' : 'text.primary' }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer || ' '}</ReactMarkdown>
              </Box>
            )
            : <Placeholder>질문을 입력하면 답변이 여기에 표시됩니다.</Placeholder>}
        </Card>

        {/* 출처 */}
        <Card variant="outlined" sx={{ p: 2, flex: 2, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Typography variant="h6" sx={{ mb: 1, flexShrink: 0 }}>
            {meta?.found === false ? '비슷한 문서' : '출처'}
            {meta?.top_score != null && <Typography component="span" color="text.secondary"> · 최고 점수 {meta.top_score.toFixed(2)}</Typography>}
          </Typography>
          {hasSources
            ? (
              <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 1 }}>
                <SourceList sources={meta.sources} />
              </Box>
            )
            : <Placeholder>{running ? '출처를 찾는 중…' : '답변에 사용된 문서가 여기에 표시됩니다.'}</Placeholder>}
        </Card>
      </Box>
    </Box>
  )
}
