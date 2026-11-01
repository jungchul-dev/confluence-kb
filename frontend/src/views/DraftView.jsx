import React, { useEffect, useState } from 'react'
import {
  Box, Typography, Button, Card, Alert, Snackbar, Table, TableHead, TableBody, TableRow, TableCell, TableContainer,
} from '@mui/material'
import * as api from '../api'
import { FONT_SIZES } from '../theme'
import DraftDialog from '../components/DraftDialog'
import { ConfirmProvider } from '../components/ConfirmDialog'

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '')

// 자료 작성 목록 — 행을 누르거나 [새 자료 작성] 을 누르면 단계별 작성 다이얼로그가 열린다
export default function DraftView({ space }) {
  const [drafts, setDrafts] = useState(null)
  const [error, setError] = useState('')
  const [dialog, setDialog] = useState(null) // { id: null(새 건) | draftId }

  const load = () => api.listDrafts().then((d) => setDrafts(d.drafts)).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <Card variant="outlined" sx={{ p: 2, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6">자료 작성</Typography>
          <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary' }}>요구사항 → 자료 선별 → 템플릿(선택) → 작성 · 검토 순서로 사내 문서를 근거로 초안을 만듭니다.</Typography>
        </Box>
        <Button variant="contained" onClick={() => setDialog({ id: null })}>새 자료 작성</Button>
      </Card>
      <Snackbar open={!!error} autoHideDuration={8000} onClose={() => setError('')} anchorOrigin={{ vertical: 'top', horizontal: 'center' }}>
        {error ? <Alert severity="error" variant="filled" onClose={() => setError('')}>{error}</Alert> : <span />}
      </Snackbar>

      <Card variant="outlined" sx={{ p: 2, mt: 2, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <Typography color="text.secondary" sx={{ mb: 1.5 }}>작성 건 {drafts?.length ?? 0}개</Typography>
      <TableContainer sx={{ flex: 1, minHeight: 0 }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>문서 이름</TableCell>
              <TableCell sx={{ width: 80 }}>형식</TableCell>
              <TableCell sx={{ width: 200 }}>템플릿</TableCell>
              <TableCell sx={{ width: 90 }} align="right">요구사항</TableCell>
              <TableCell sx={{ width: 90 }} align="right">고른 자료</TableCell>
              <TableCell sx={{ width: 100 }} align="right">작성</TableCell>
              <TableCell sx={{ width: 150 }}>수정</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {drafts?.map((d) => (
              <TableRow key={d.id} hover onClick={() => setDialog({ id: d.id })} sx={{ cursor: 'pointer' }}>
                <TableCell>
                  <Typography sx={{ fontWeight: 500, fontSize: FONT_SIZES.md }}>{d.name}</Typography>
                  {d.overview && <Typography noWrap sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', maxWidth: 560 }}>{d.overview}</Typography>}
                </TableCell>
                <TableCell sx={{ fontSize: FONT_SIZES.sm, textTransform: 'uppercase' }}>{d.doc_format}</TableCell>
                <TableCell><Typography noWrap sx={{ fontSize: FONT_SIZES.sm, color: d.template_name ? 'text.primary' : 'text.disabled', maxWidth: 190 }}>{d.template_name || '없음'}</Typography></TableCell>
                <TableCell align="right">{d.requirement_count}</TableCell>
                <TableCell align="right">{d.selected_count}</TableCell>
                <TableCell align="right">{d.section_count ? `${d.written_count} / ${d.section_count}` : '-'}</TableCell>
                <TableCell sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary' }}>{fmtDate(d.updated_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {drafts?.length === 0 && (
          <Box sx={{ py: 8, textAlign: 'center', color: 'text.secondary' }}>
            <Typography sx={{ mb: 1 }}>아직 작성한 자료가 없습니다.</Typography>
            <Typography sx={{ fontSize: FONT_SIZES.sm }}>[새 자료 작성] 을 눌러 문서 이름과 개요를 적고 시작하세요.</Typography>
          </Box>
        )}
      </TableContainer>
      </Card>

      <ConfirmProvider>
        <DraftDialog open={!!dialog} draftId={dialog?.id || null} space={space} onChanged={load} onClose={() => { setDialog(null); load() }} />
      </ConfirmProvider>
    </Box>
  )
}
