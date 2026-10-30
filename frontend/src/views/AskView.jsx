import React, { useRef, useState } from 'react'
import { Box, Typography, TextField, Button, Card, Alert } from '@mui/material'
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
    <Box>
      <Box component="form" sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', mb: 2 }} onSubmit={submit}>
        <TextField
          multiline fullWidth minRows={5}
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

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {(answer || running) && (
        <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            답변
            {running && <Typography component="span" color="text.secondary"> · 생성 중…</Typography>}
            {done && <Typography component="span" color="text.secondary"> · {(done.latency_ms / 1000).toFixed(1)}s</Typography>}
          </Typography>
          <Box sx={{ lineHeight: 1.6, color: meta?.found === false ? 'text.secondary' : 'text.primary' }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer || ' '}</ReactMarkdown>
          </Box>
        </Card>
      )}

      {meta?.sources?.length > 0 && (
        <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {meta.found === false ? '비슷한 문서' : '출처'}
            {meta.top_score != null && <Typography component="span" color="text.secondary"> · 최고 점수 {meta.top_score.toFixed(2)}</Typography>}
          </Typography>
          <SourceList sources={meta.sources} />
        </Card>
      )}

      {!answer && !running && !error && (
        <Box sx={{ textAlign: 'center', py: 5, color: 'text.secondary' }}>
          질문을 입력하면 Confluence 문서를 기반으로 답변합니다.
        </Box>
      )}
    </Box>
  )
}
