import React, { createContext, useCallback, useContext, useRef, useState } from 'react'
import { Button, Dialog, DialogActions, DialogContent, Typography } from '@mui/material'
import { FONT_SIZES } from '../theme'

// 브라우저 기본 confirm 대신 쓰는 MUI 확인 창 (문구 + 취소 / 확인).
// const confirm = useConfirm(); if (await confirm('지울까요?', { ok: '지우기', danger: true })) { ... }
const ConfirmContext = createContext(null)

export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null) // { message, ok, danger }
  const resolver = useRef(null)

  const confirm = useCallback((message, { ok = '확인', danger = false } = {}) => new Promise((resolve) => {
    resolver.current = resolve
    setState({ message, ok, danger })
  }), [])

  const finish = (value) => {
    resolver.current?.(value)
    resolver.current = null
    setState(null)
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <Dialog open={!!state} onClose={() => finish(false)} maxWidth={false} slotProps={{ paper: { sx: { width: 480, maxWidth: 'calc(100% - 48px)' } } }}>
        <DialogContent sx={{ px: 3, pt: '28px !important', pb: 2.5 }}>
          <Typography sx={{ fontSize: FONT_SIZES.md, lineHeight: 1.7, whiteSpace: 'pre-line' }}>{state?.message}</Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2.5, gap: 0.5 }}>
          <Button size="small" variant="outlined" onClick={() => finish(false)}>취소</Button>
          <Button size="small" variant="contained" color={state?.danger ? 'error' : 'primary'} onClick={() => finish(true)} autoFocus>{state?.ok}</Button>
        </DialogActions>
      </Dialog>
    </ConfirmContext.Provider>
  )
}

export const useConfirm = () => {
  const confirm = useContext(ConfirmContext)
  if (!confirm) throw new Error('useConfirm 은 ConfirmProvider 안에서만 쓸 수 있습니다.')
  return confirm
}
