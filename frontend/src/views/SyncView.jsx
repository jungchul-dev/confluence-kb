import React, { useCallback, useEffect, useState } from 'react'
import { Box, Typography, Button, Card, Table, TableHead, TableBody, TableRow, TableCell, Alert, IconButton } from '@mui/material'
import { Refresh } from '@mui/icons-material'
import * as api from '../api'

const fmt = (iso) => (iso ? new Date(iso).toLocaleString('ko-KR') : '-')

export default function SyncView() {
  const [status, setStatus] = useState(null)
  const [errors, setErrors] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([api.syncStatus(), api.syncErrors()])
      setStatus(s); setErrors(e); setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  const run = async (mode) => {
    setBusy(true)
    try {
      await api.runSync(mode)
      setTimeout(load, 1000)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }}>
        <Button variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} onClick={() => run('incremental')} disabled={busy || status?.running}>증분 동기화</Button>
        <Button variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} onClick={() => run('full')} disabled={busy || status?.running}>전체 동기화</Button>
        {status?.running && <Typography color="text.secondary">실행 중…</Typography>}
        <IconButton size="small" onClick={load} aria-label="새로고침"><Refresh fontSize="small" /></IconButton>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>공간</Typography>
        <Table size="small">
          <TableHead><TableRow><TableCell>공간</TableCell><TableCell>전체 문서</TableCell><TableCell>페이지</TableCell><TableCell>첨부</TableCell><TableCell>오류</TableCell><TableCell>마지막 동기화</TableCell></TableRow></TableHead>
          <TableBody>
            {(status?.spaces || []).map((s) => (
              <TableRow key={s.space_key}>
                <TableCell>{s.space_key}</TableCell><TableCell>{s.documents}</TableCell><TableCell>{s.pages}</TableCell><TableCell>{s.attachments ?? 0}</TableCell>
                <TableCell sx={{ color: s.errors ? 'error.main' : 'inherit' }}>{s.errors}</TableCell><TableCell>{fmt(s.last_synced_at)}</TableCell>
              </TableRow>
            ))}
            {status && status.spaces.length === 0 && <TableRow><TableCell colSpan={6} align="center" color="text.secondary">CONFLUENCE_SPACES 가 비어 있습니다.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>

      <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>최근 실행</Typography>
        <Table size="small">
          <TableHead><TableRow><TableCell>시작</TableCell><TableCell>공간</TableCell><TableCell>모드</TableCell><TableCell>상태</TableCell><TableCell>조회</TableCell><TableCell>색인</TableCell><TableCell>첨부</TableCell><TableCell>삭제</TableCell><TableCell>오류</TableCell></TableRow></TableHead>
          <TableBody>
            {(status?.runs || []).map((r) => (
              <TableRow key={r.id}>
                <TableCell>{fmt(r.started_at)}</TableCell><TableCell>{r.space_key}</TableCell><TableCell>{(r.mode || '').toUpperCase()}</TableCell>
                <TableCell sx={{ color: r.status === 'failed' ? 'error.main' : r.status === 'success' ? 'success.main' : 'inherit' }}>
                  {(r.status || '').toUpperCase()}{r.status === 'failed' && r.message && <Typography component="span" color="text.secondary" sx={{ fontSize: '0.75rem', ml: 0.5, maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block', verticalAlign: 'bottom' }} title={r.message}>· {r.message}</Typography>}
                </TableCell>
                <TableCell>{r.pages_seen}</TableCell><TableCell>{r.pages_indexed}</TableCell><TableCell>{r.attachments_indexed}</TableCell><TableCell>{r.pages_deleted}</TableCell><TableCell sx={{ color: r.errors ? 'error.main' : 'inherit' }}>{r.errors}</TableCell>
              </TableRow>
            ))}
            {status && status.runs.length === 0 && <TableRow><TableCell colSpan={9} align="center" color="text.secondary">아직 실행 기록이 없습니다.</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>

      {errors.length > 0 && (
        <Card variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>페이지 오류 ({errors.length})</Typography>
          <Table size="small">
            <TableHead><TableRow><TableCell>페이지 id</TableCell><TableCell>공간</TableCell><TableCell>버전</TableCell><TableCell>시각</TableCell><TableCell>오류</TableCell></TableRow></TableHead>
            <TableBody>
              {errors.map((e) => (
                <TableRow key={e.page_id}><TableCell>{e.page_id}</TableCell><TableCell>{e.space_key}</TableCell><TableCell>{e.version}</TableCell><TableCell>{fmt(e.synced_at)}</TableCell><TableCell sx={{ color: 'error.main' }}>{e.error}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </Box>
  )
}
