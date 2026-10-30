import React, { useState } from 'react'
import { Box, Typography, Divider } from '@mui/material'
import AskView from './views/AskView'
import SearchView from './views/SearchView'
import SyncView from './views/SyncView'
import AnalyticsView from './views/AnalyticsView'
import { BORDER, HOVER_BG, SELECTED_BG, STRONG_TEXT, MUTED_TEXT } from './theme'

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
      borderRadius: 1.5, cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500,
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

  return (
    <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden', backgroundColor: 'background.default' }}>
      <Box sx={{ width: 240, flexShrink: 0, borderRight: BORDER, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ height: 56, flexShrink: 0, px: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ width: 90, height: 28, borderRadius: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: STRONG_TEXT, color: 'background.paper', fontWeight: 700, fontSize: '0.8125rem' }}>SCP 실행그룹</Box>
          <Typography noWrap sx={{ fontWeight: 600, fontSize: '0.9375rem', letterSpacing: '-0.01em' }}>Confluence KB</Typography>
        </Box>
        <Box sx={{ px: 1.5, py: 1, flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.key} label={item.label} isActive={tab === item.key} onClick={() => setTab(item.key)} />
          ))}
          <Divider sx={{ my: 1.5 }} />
          <Typography variant="caption" sx={{ display: 'block', px: 1.25, mb: 0.5, fontWeight: 600, fontSize: '0.6875rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'text.disabled' }}>관리자</Typography>
          {ADMIN_ITEMS.map((item) => (
            <NavItem key={item.key} label={item.label} isActive={tab === item.key} onClick={() => setTab(item.key)} />
          ))}
        </Box>
      </Box>

      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ height: 56, flexShrink: 0, px: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: BORDER }}>
          <Typography noWrap sx={{ fontWeight: 600, fontSize: '1rem', letterSpacing: '-0.01em' }}>{VIEW_TITLES[tab]}</Typography>
          <Typography sx={{ fontSize: '0.8125rem', color: 'text.secondary' }}>{localStorage.getItem('userId') || ''}</Typography>
        </Box>
        <Box sx={{ flex: 1, overflow: 'auto', px: 3, py: 2.5 }}>
          {tab === 'ask' && <AskView />}
          {tab === 'search' && <SearchView />}
          {tab === 'analytics' && <AnalyticsView />}
          {tab === 'sync' && <SyncView />}
        </Box>
      </Box>
    </Box>
  )
}
