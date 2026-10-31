import React from 'react'
import { Box, Typography, Chip } from '@mui/material'
import { ChevronRight as ChevronRightIcon, Article as ArticleIcon, AttachFile as AttachFileIcon } from '@mui/icons-material'
import { FONT_SIZES } from '../theme'

export const KindChip = ({ kind }) => {
  const c = kind === 'attachment' ? '#7c3aed' : '#0e7490'
  return (
    <Chip size="small" icon={kind === 'attachment' ? <AttachFileIcon sx={{ fontSize: 15 }} /> : <ArticleIcon sx={{ fontSize: 15 }} />} label={kind === 'attachment' ? '첨부' : '페이지'} variant="filled" sx={{ flexShrink: 0, height: 22, fontSize: FONT_SIZES.xs, backgroundColor: c, color: '#fff', '& .MuiChip-icon': { ml: 0.75, mr: -0.5, color: '#fff' } }} />
  )
}

export const Breadcrumb = ({ path, heading, dateStr }) => {
  const parts = path.split(/\s*>\s*/).filter(Boolean)
  const trimmed = parts.length > 1 ? parts.slice(1) : parts
  if (heading) trimmed.push(heading)
  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', rowGap: 0.25 }}>
        {trimmed.map((p, i) => (
          <React.Fragment key={i}>
            {i > 0 && <ChevronRightIcon sx={{ fontSize: 14, color: 'text.disabled', mx: 0.25 }} />}
            <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{p}</Typography>
          </React.Fragment>
        ))}
      </Box>
      {dateStr && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.disabled', mt: 0.25 }}>수정 {dateStr}</Typography>}
    </Box>
  )
}
