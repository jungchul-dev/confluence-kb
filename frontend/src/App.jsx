import React, { useEffect, useState } from 'react'
import { Box, Typography, Divider, MenuItem, Select, FormControl, Checkbox, CircularProgress } from '@mui/material'
import AskView from './views/AskView'
import SearchView from './views/SearchView'
import SyncView from './views/SyncView'
import AnalyticsView from './views/AnalyticsView'
import * as api from './api'
import { BORDER, HOVER_BG, SELECTED_BG, STRONG_TEXT, MUTED_TEXT, FONT_SIZES } from './theme'

const NAV_ITEMS = [
  { key: 'ask', label: '질문' },
  { key: 'search', label: '검색' },
  { key: 'analytics', label: '분석' },
]
const ADMIN_ITEMS = [
  { key: 'sync', label: '동기화' },
]
const VIEW_TITLES = { ask: '질문', search: '검색', analytics: '분석', sync: '동기화' }

const NavItem = ({ label, isActive, onClick }) => (
  <Box
    onClick={onClick}
    sx={{
      display: 'flex', alignItems: 'center', height: 34, px: 1.25, mb: 0.25,
      borderRadius: 1.5, cursor: 'pointer', fontSize: FONT_SIZES.lg, fontWeight: 500,
      backgroundColor: isActive ? SELECTED_BG : 'transparent',
      color: isActive ? STRONG_TEXT : MUTED_TEXT,
      transition: 'background-color 0.12s, color 0.12s',
      '&:hover': { backgroundColor: isActive ? SELECTED_BG : HOVER_BG, color: STRONG_TEXT },
    }}
  >
    {label}
  </Box>
)

export default function App() {
  const [tab, setTab] = useState('ask')
  const [space, setSpace] = useState([])
  const [spaces, setSpaces] = useState([])
  const [spacesLoading, setSpacesLoading] = useState(true)

  useEffect(() => {
    api.getSpaces().then(setSpaces).catch(() => {}).finally(() => setSpacesLoading(false))
  }, [])

  const showSpaceFilter = tab === 'ask' || tab === 'search' || tab === 'analytics'
  const spaceLabel = space.length === 0 ? '전체 공간' : space.length === 1 ? space[0] : `${space[0]} 외 ${space.length - 1}`

  return (
    <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden', backgroundColor: 'background.default' }}>
      <Box sx={{ width: 250, flexShrink: 0, borderRight: BORDER, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ height: 56, flexShrink: 0, px: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ width: 90, height: 28, borderRadius: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: STRONG_TEXT, color: 'background.paper', fontWeight: 700, fontSize: FONT_SIZES.sm }}>SCP 실행그룹</Box>
      <Typography noWrap sx={{ fontWeight: 600, fontSize: FONT_SIZES.lg, letterSpacing: '-0.01em' }}>Confluence KB</Typography>
        </Box>
        <Box sx={{ px: 2.5, py: 2, flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.key} label={item.label} isActive={tab === item.key} onClick={() => setTab(item.key)} />
          ))}
          <Divider sx={{ my: 1.5 }} />
        <Typography variant="caption" sx={{ display: 'block', px: 1.25, mb: 0.5, fontWeight: 600, fontSize: FONT_SIZES.xs, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'text.disabled' }}>관리자</Typography>
          {ADMIN_ITEMS.map((item) => (
            <NavItem key={item.key} label={item.label} isActive={tab === item.key} onClick={() => setTab(item.key)} />
          ))}
        </Box>
      </Box>

      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ height: 56, flexShrink: 0, px: 5, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: BORDER }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography noWrap sx={{ fontWeight: 600, fontSize: FONT_SIZES.xl, letterSpacing: '-0.01em' }}>{VIEW_TITLES[tab]}</Typography>
            {showSpaceFilter && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary' }}>공간</Typography>
                <FormControl size="small" sx={{ minWidth: 200 }}>
                <Select multiple value={space} onChange={(e) => { const v = typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value; if (v.includes('__all__')) { setSpace(space.length === spaces.length ? [] : spaces.map((s) => s.space_key)); return } setSpace(v) }} displayEmpty renderValue={() => spaceLabel} MenuProps={{ PaperProps: { sx: { maxHeight: 400 } } }}>
                  <MenuItem value="__all__" sx={{ py: 0, minHeight: 32, pl: 1 }}>
                    <Checkbox checked={space.length === spaces.length} indeterminate={space.length > 0 && space.length < spaces.length} size="small" />
                    <Typography sx={{ fontSize: FONT_SIZES.md, fontWeight: 600 }}>모두 선택</Typography>
                  </MenuItem>
                  <Divider sx={{ my: 0 }} />
                  {spacesLoading && <MenuItem disabled><CircularProgress size={16} sx={{ mr: 1 }} /> 불러오는 중…</MenuItem>}
                  {spaces.map((s) => (
                    <MenuItem key={s.space_key} value={s.space_key} sx={{ py: 0, minHeight: 32, pl: 1 }}>
                      <Checkbox checked={space.indexOf(s.space_key) > -1} size="small" />
                      <Typography sx={{ fontSize: FONT_SIZES.md }}>{s.space_key} ({s.doc_count})</Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              </Box>
            )}
          </Box>
          <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary' }}>{localStorage.getItem('userId') || ''}</Typography>
        </Box>
        <Box sx={{ flex: 1, overflow: 'auto', px: 5, py: 4 }}>
          {tab === 'ask' && <AskView space={space} />}
          {tab === 'search' && <SearchView space={space} />}
          {tab === 'analytics' && <AnalyticsView space={space} />}
          {tab === 'sync' && <SyncView />}
        </Box>
      </Box>
    </Box>
  )
}
