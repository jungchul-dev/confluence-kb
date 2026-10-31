import React from 'react'
import { Box, Typography, Chip } from '@mui/material'
import { ChevronRight as ChevronRightIcon, Article as ArticleIcon, AttachFile as AttachFileIcon } from '@mui/icons-material'
import { FONT_SIZES } from '../theme'

export const KindChip = ({ kind }) => (
  <Chip size="small" icon={kind === 'attachment' ? <AttachFileIcon sx={{ fontSize: 15 }} /> : <ArticleIcon sx={{ fontSize: 15 }} />} label={kind === 'attachment' ? '첨부' : '페이지'} color={kind === 'attachment' ? 'success' : 'primary'} variant="filled" sx={{ flexShrink: 0, '& .MuiChip-icon': { ml: 0.75, mr: -0.5 } }} />
)

export const Breadcrumb = ({ path, heading, spaceKey, dateStr }) => {
  const parts = path.split(/\s*>\s*/).filter(Boolean)
  if (heading) parts.push(heading)
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', rowGap: 0.25 }}>
      {parts.map((p, i) => (
        <React.Fragment key={i}>
          {i > 0 && <ChevronRightIcon sx={{ fontSize: 14, color: 'text.disabled', mx: 0.25 }} />}
          <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{p}</Typography>
        </React.Fragment>
      ))}
      {spaceKey && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.disabled', ml: 0.5 }}>· {spaceKey}</Typography>}
      {dateStr && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.disabled', ml: 0.5 }}>· 수정 {dateStr}</Typography>}
    </Box>
  )
}
