import React from 'react'
import { Box, Typography, Chip, Tooltip } from '@mui/material'
import { MONO_FONT, FONT_SIZES } from '../theme'
import { KindChip, Breadcrumb } from './shared'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }) : '')

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
              <Box component="span" sx={{ fontFamily: MONO_FONT, fontSize: FONT_SIZES.xs, color: 'text.secondary', flexShrink: 0 }}>[{s.index}]</Box>
              <KindChip kind={s.kind} />
              <Typography noWrap sx={{ fontWeight: 500, minWidth: 0 }}>{s.title}</Typography>
              {!isCited && (
                <Tooltip title="검색 후보에는 올랐지만 답변에 인용되지 않은 문서입니다">
                  <Chip size="small" label="미인용" variant="outlined" sx={{ ml: 'auto', flexShrink: 0, color: 'text.disabled', borderStyle: 'dashed', height: 22, fontSize: FONT_SIZES.xs }} />
                </Tooltip>
              )}
              {isCited && (
                <Tooltip title={`관련도 ${s.score.toFixed(3)}`}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 'auto', flexShrink: 0 }}>
                    <Box sx={{ width: 60, height: 4, borderRadius: 2, backgroundColor: 'action.hover', overflow: 'hidden' }}>
                      <Box sx={{ width: `${Math.round(s.score * 100)}%`, height: '100%', backgroundColor: s.score >= 0.7 ? '#16a34a' : s.score >= 0.4 ? '#d97706' : '#a1a1aa' }} />
                    </Box>
                    <Typography sx={{ fontFamily: MONO_FONT, fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{Math.round(s.score * 100)}%</Typography>
                  </Box>
                </Tooltip>
              )}
            </Box>
            <Box sx={{ mt: 0.5 }}>
              <Breadcrumb path={s.path} dateStr={fmtDate(s.updated_at)} />
            </Box>
          </Box>
        )
      })}
    </Box>
  )
}
