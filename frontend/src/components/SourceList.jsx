import React from 'react'
import { Box, Typography, Chip, Link } from '@mui/material'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

export default function SourceList({ sources }) {
  return (
    <Box component="ol" sx={{ listStyle: 'none', p: 0, m: 0 }}>
      {sources.map((s) => (
        <Box key={s.document_id} component="li" sx={{ py: 1, borderTop: 1, borderColor: 'divider', '&:first-of-type': { borderTop: 0 } }}>
          <Box component="span" sx={{ fontFamily: 'monospace', color: 'text.secondary', mr: 1, fontSize: '0.75rem' }}>[{s.index}]</Box>
          <Link href={s.url} target="_blank" rel="noreferrer" sx={{ fontWeight: 500 }}>{s.title}</Link>
          <Chip size="small" label={s.kind === 'attachment' ? '첨부' : '페이지'} color={s.kind === 'attachment' ? 'success' : 'primary'} variant="filled" sx={{ ml: 1 }} />
          <Typography sx={{ fontSize: '0.75rem', ml: 3, color: 'text.secondary' }}>{s.path} · 수정 {fmtDate(s.updated_at)} · 점수 {s.score.toFixed(2)}</Typography>
        </Box>
      ))}
    </Box>
  )
}
