import React from 'react'
import { Box, Typography, Chip, Tooltip } from '@mui/material'
import { MONO_FONT } from '../theme'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

// 답변의 출처 목록. 검색 결과·분석 목록과 같은 카드 형태.
// cited: 답변 본문에 [n] 으로 실제 인용된 번호 집합. 없으면 전부 인용된 것으로 본다.
export default function SourceList({ sources, cited }) {
  return (
    <Box>
      {sources.map((s) => {
        const isCited = !cited || cited.has(s.index)
        return (
          <Box
            key={s.document_id}
            component="a"
            href={s.url}
            target="_blank"
            rel="noreferrer"
            sx={{
              display: 'block', p: 1.25, mb: 0.75, borderRadius: 1.5, border: 1, borderColor: 'divider',
              color: 'inherit', textDecoration: 'none', cursor: 'pointer', opacity: isCited ? 1 : 0.6,
              '&:hover': { backgroundColor: 'action.hover', borderColor: 'borderStrong', opacity: 1 },
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
              <Box component="span" sx={{ fontFamily: MONO_FONT, fontSize: '0.75rem', color: 'text.secondary', flexShrink: 0 }}>[{s.index}]</Box>
              <Chip size="small" label={s.kind === 'attachment' ? '첨부' : '페이지'} color={s.kind === 'attachment' ? 'success' : 'primary'} variant="filled" sx={{ flexShrink: 0 }} />
              <Typography noWrap sx={{ fontWeight: 500, minWidth: 0 }}>{s.title}</Typography>
              {!isCited && (
                <Tooltip title="검색 후보에는 올랐지만 답변에 인용되지 않은 문서입니다">
                  <Chip size="small" label="미인용" variant="outlined" sx={{ ml: 'auto', flexShrink: 0, color: 'text.disabled', borderStyle: 'dashed', height: 22, fontSize: '0.75rem' }} />
                </Tooltip>
              )}
            </Box>
            <Typography noWrap sx={{ fontSize: '0.75rem', mt: 0.5, color: 'text.secondary' }}>
              {s.path} · 수정 {fmtDate(s.updated_at)} · 관련도 {Math.round(s.score * 100)}%
            </Typography>
          </Box>
        )
      })}
    </Box>
  )
}
