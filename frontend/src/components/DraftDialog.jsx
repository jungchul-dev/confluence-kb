import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  Box, Typography, TextField, Button, Card, Chip, Alert, Checkbox, IconButton, Tooltip, CircularProgress,
  Select, MenuItem, Link, LinearProgress, Dialog, DialogContent, DialogActions, Stepper, Step, StepButton, StepLabel,
  ToggleButtonGroup, ToggleButton, Snackbar, Collapse, MobileStepper,
} from '@mui/material'
import {
  PushPin as PinIcon, PushPinOutlined as PinOutlinedIcon, DeleteOutlined as DeleteIcon, OpenInNew as OpenInNewIcon,
  CheckCircle as CheckIcon, Cancel as CrossIcon, RadioButtonUnchecked as UnknownIcon, UploadFile as UploadIcon, Download as DownloadIcon,
  ArrowUpward as UpIcon, ArrowDownward as DownIcon, Close as CloseIcon, Add as AddIcon, KeyboardArrowRight as NextIcon, KeyboardArrowLeft as PrevIcon, ExpandMore as ExpandIcon, WarningAmberOutlined as WarnIcon,
  DescriptionOutlined as DocxIcon, SlideshowOutlined as PptxIcon, InsertDriveFileOutlined as FileIcon,
} from '@mui/icons-material'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import * as api from '../api'
import { FONT_SIZES, MONO_FONT } from '../theme'
import { Breadcrumb } from './Common'

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '')

const Empty = ({ children }) => (
  <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 1.5, alignItems: 'center', justifyContent: 'center', color: 'text.disabled', fontSize: FONT_SIZES.md, textAlign: 'center', px: 2, py: 4 }}>{children}</Box>
)

const Working = ({ children }) => (
  <Empty><CircularProgress size={22} /><Typography sx={{ fontSize: FONT_SIZES.md, color: 'text.secondary' }}>{children}</Typography></Empty>
)

const Hint = ({ children, sx }) => <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary', mb: 1.5, ...sx }}>{children}</Typography>

// 좁은 칸용 한 줄 경로: 공간 키를 빼고 "… > 상위 > 소제목" 으로 줄인다. 전체 경로는 툴팁
const ShortPath = ({ path, heading }) => {
  const parts = (path || '').split(/\s*>\s*/).filter(Boolean).slice(1)
  const full = [...parts, heading].filter(Boolean).join(' > ')
  const short = [...parts.slice(-1), heading].filter(Boolean).join(' > ')
  return (
    <Tooltip title={full}>
      <Typography noWrap sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{parts.length > 1 ? '… > ' : ''}{short}</Typography>
    </Tooltip>
  )
}

const CoverageIcon = ({ covered, note }) => (
  <Tooltip title={note || (covered == null ? '아직 점검 전 (본문을 생성하면 점검합니다)' : covered ? '본문에 반영됨' : '본문에 빠짐')}>
    {covered == null ? <UnknownIcon sx={{ fontSize: 18, color: 'text.disabled' }} />
      : covered ? <CheckIcon sx={{ fontSize: 18, color: '#16a34a' }} /> : <CrossIcon sx={{ fontSize: 18, color: '#dc2626' }} />}
  </Tooltip>
)

// ───────── 기본 정보 ─────────
export const FORMAT_LABEL = { docx: '보고서 (docx)', pptx: '발표 자료 (pptx)' }

function InfoStep({ name, setName, overview, setOverview, docFormat, setDocFormat, formLocked }) {
  return (
    <Box sx={{ maxWidth: 760, width: '100%', mx: 'auto', pt: 2 }}>
      <Hint sx={{ mb: 3 }}>작성할 문서의 이름 · 형식 · 개요를 적으세요. 개요는 목차 제안 · 자료 검색 · 본문 작성에 함께 쓰입니다.</Hint>
      <TextField size="small" fullWidth label="문서 이름" placeholder="예: 3분기 서비스 운영 보고서" value={name} onChange={(e) => setName(e.target.value)} sx={{ mb: 3 }} autoFocus />
      <Typography sx={{ fontSize: FONT_SIZES.sm, color: 'text.secondary', mb: 1 }}>문서 형식</Typography>
      <ToggleButtonGroup size="small" exclusive value={docFormat} onChange={(_, v) => v && setDocFormat(v)} disabled={formLocked} sx={{ mb: formLocked ? 1 : 3 }}>
        <ToggleButton value="docx" sx={{ px: 2, gap: 1 }}><DocxIcon fontSize="small" />{FORMAT_LABEL.docx}</ToggleButton>
        <ToggleButton value="pptx" sx={{ px: 2, gap: 1 }}><PptxIcon fontSize="small" />{FORMAT_LABEL.pptx}</ToggleButton>
      </ToggleButtonGroup>
      {formLocked && <Hint sx={{ mb: 3 }}>템플릿이 올라가 있어 형식을 바꿀 수 없습니다. 템플릿 단계에서 템플릿을 지우면 바꿀 수 있습니다.</Hint>}
      <TextField size="small" fullWidth multiline minRows={6} label="작성 개요 — 목적 · 대상 · 범위" placeholder="문서의 목적 · 대상(독자) · 범위 · 기간 등을 몇 줄로" value={overview} onChange={(e) => setOverview(e.target.value)} />
    </Box>
  )
}

// ───────── 요구사항 ─────────
function RequirementsStep({ draft, reload, setDraft, busy, setBusy, setError, notify }) {
  const fileRef = useRef(null)
  const [newReq, setNewReq] = useState('')
  const [adding, setAdding] = useState(false)

  const upload = async (file) => {
    if (!file) return
    setBusy('요구사항 파일을 읽고 항목을 뽑는 중…'); setError('')
    try { const d = await api.uploadRequirementFile(draft.id, file); setDraft(d); notify(`${file.name} 에서 요구사항 ${d.extracted}건을 뽑았습니다.`) } catch (e) { setError(e.message) } finally { setBusy('') }
  }
  const act = async (fn) => { setError(''); try { const d = await fn(); if (d) setDraft(d); else await reload() } catch (e) { setError(e.message) } }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 1.5 }}>
        <Box component="form" sx={{ display: 'flex', gap: 1, flex: 1 }} onSubmit={async (e) => {
          e.preventDefault(); if (!newReq.trim() || adding) return
          setAdding(true); await act(() => api.addRequirement(draft.id, newReq.trim())); setNewReq(''); setAdding(false)
        }}>
          <TextField size="small" fullWidth value={newReq} onChange={(e) => setNewReq(e.target.value)} placeholder="요구사항 직접 추가" disabled={adding} />
          <Button type="submit" size="small" variant="outlined" startIcon={adding ? <CircularProgress size={14} /> : <AddIcon />} disabled={!newReq.trim() || adding} sx={{ flexShrink: 0, whiteSpace: 'nowrap', minWidth: 84 }}>{adding ? '추가 중' : '추가'}</Button>
        </Box>
        <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.pptx,.xlsx,.md,.txt" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = '' }} />
        <Button variant="contained" size="small" startIcon={<UploadIcon />} onClick={() => fileRef.current?.click()} disabled={!!busy} sx={{ flexShrink: 0, whiteSpace: 'nowrap', ml: 2 }}>요구사항 파일 올리기</Button>
      </Box>
      {draft.files.length > 0 && (
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mb: 1.5 }}>
          {draft.files.map((f) => (
            <Chip key={f.id} size="small" icon={<FileIcon />} label={`${f.file_name} · ${f.chars.toLocaleString()}자`} onDelete={() => window.confirm(`${f.file_name} 과 여기서 뽑은 요구사항을 지울까요?`) && act(() => api.deleteRequirementFile(draft.id, f.id))} />
          ))}
        </Box>
      )}
      <Hint>요구사항 문서를 올리면 항목을 뽑습니다. 요구사항은 목차를 만들 때 함께 참고하고, 목차마다 나눠 붙여 자료 검색과 본문 작성에 씁니다. 요구사항이 없으면 건너뛰어도 됩니다.</Hint>
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
        {draft.requirements.length === 0 && <Empty>아직 요구사항이 없습니다. 파일을 올리거나 위에 직접 입력하세요.</Empty>}
        {draft.requirements.map((r) => (
          <Box key={r.id} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.75, borderBottom: 1, borderColor: 'divider' }}>
            <Typography sx={{ width: 90, flexShrink: 0, fontFamily: MONO_FONT, fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{r.code || '-'}</Typography>
            <Typography sx={{ flex: 1, fontSize: FONT_SIZES.md }}>{r.content}</Typography>
            <IconButton size="small" onClick={() => act(() => api.deleteRequirement(draft.id, r.id))}><DeleteIcon fontSize="small" /></IconButton>
          </Box>
        ))}
      </Box>
    </Box>
  )
}

// ───────── 자료 선별 (목차 다듬기 포함) ─────────
function SourcesStep({ draft, reload, setDraft, busy, setBusy, setError, space, proposeAndCollect, pending, setPending, flushRef }) {
  const [sectionId, setSectionId] = useState(draft.sections[0]?.id)
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState(null)
  // 고친 목차 제목 · 찾을 내용 · 작성 지침은 화면에만 들고 있다가 단계를 옮기거나(stepper) 닫을 때 한꺼번에 저장한다 (입력마다 서버를 부르지 않는다)
  const [edits, setEdits] = useState({}) // { 목차 id: { title, query, guide } }
  const [newTitle, setNewTitle] = useState('')
  const section = draft.sections.find((s) => s.id === sectionId)
  const valuesOf = (s) => edits[s.id] || { title: s.title, query: s.query, guide: s.guide }
  const form = section ? valuesOf(section) : { title: '', query: '', guide: '' }
  const setForm = (next) => setEdits((e) => ({ ...e, [sectionId]: next }))
  // 다시 모으는 중인 목차 (pending.sectionId 가 null 이면 전체)
  const isCollecting = (sid) => pending?.kind === 'collect' && (!pending.sectionId || pending.sectionId === sid)
  const collectingHere = isCollecting(sectionId)

  // 목차가 통째로 바뀌면(다시 제안 · 템플릿) 지금 고른 목차가 사라지므로 첫 목차로 옮긴다
  useEffect(() => { if (!section) setSectionId(draft.sections[0]?.id) }, [draft.sections, section])

  const load = useCallback(async () => {
    // 사라진 목차 id 로 부르면 404(목차를 찾을 수 없습니다) 가 나므로, 지금 목차에 있는 id 만 읽는다
    if (!sectionId || !draft.sections.some((s) => s.id === sectionId)) { setSources([]); return }
    setLoading(true)
    try { setSources((await api.listSources(draft.id, sectionId)).sources) } catch (e) { setError(e.message) } finally { setLoading(false) }
  }, [draft.id, sectionId, setError]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setPreview(null) }, [sectionId])
  // 목차를 바꾸거나, 밖에서 후보가 바뀌었거나(전체 모으기 등), 모으기가 끝나면 다시 읽는다
  useEffect(() => { if (collectingHere) { setSources([]); setPreview(null) } else load() }, [load, section?.source_count, collectingHere])

  // 목차 하나 저장 — 바뀐 칸만 보낸다. 다시 제안 · 삭제로 사라진 목차는 건너뛴다
  const saveOne = async (sid) => {
    const s = draft.sections.find((x) => x.id === sid)
    const e = edits[sid]
    if (s && e) {
      const body = {}
      for (const k of ['title', 'query', 'guide']) if (e[k] !== s[k] && (k !== 'title' || e.title.trim())) body[k] = e[k]
      if (Object.keys(body).length) setDraft(await api.updateDraftSection(draft.id, sid, body))
    }
    setEdits((prev) => { const { [sid]: _, ...rest } = prev; return rest })
  }
  const saveAll = async () => { for (const sid of Object.keys(edits)) await saveOne(sid) }
  // 단계 이동 · 닫기 때 다이얼로그가 부른다
  if (flushRef) flushRef.current = { save: saveAll, dirty: Object.keys(edits).length > 0 }
  const collect = async (one) => {
    setBusy(one ? '이 목차의 자료를 다시 모으는 중…' : '모든 목차의 자료를 모으는 중…'); setPending({ kind: 'collect', sectionId: one ? sectionId : null })
    try {
      await (one ? saveOne(sectionId) : saveAll()) // 모으기 전에 고친 찾을 내용을 먼저 저장한다
      setDraft(await api.collectSources(draft.id, one ? sectionId : null, space))
    } catch (e) { setError(e.message) } finally { setBusy(''); setPending(null) }
  }
  const act = async (fn) => { setError(''); try { setDraft(await fn()) } catch (e) { setError(e.message) } }
  const move = (d) => {
    const ids = draft.sections.map((s) => s.id); const i = ids.indexOf(sectionId); const j = i + d
    if (j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    act(() => api.reorderSections(draft.id, ids))
  }
  const removeSection = () => window.confirm(`목차 "${section.title}" 와 그 자료를 지울까요? 배정된 요구사항은 미배정이 됩니다.`) && act(() => api.deleteSection(draft.id, sectionId))
  const addSection = async (e) => {
    e.preventDefault(); if (!newTitle.trim()) return
    await act(() => api.addSection(draft.id, newTitle.trim())); setNewTitle('')
  }
  const toggle = async (s, body) => {
    setSources((prev) => prev.map((x) => (x.id === s.id ? { ...x, ...body, ...(body.pinned ? { selected: true } : {}) } : x)))
    try { await api.updateSource(draft.id, s.id, body); reload() } catch (e) { setError(e.message); load() }
  }
  const remove = async (s) => { try { await api.deleteSource(draft.id, s.id); await load(); reload() } catch (e) { setError(e.message) } }
  // 이 목차에 붙은 요구사항 · 다른 곳(다른 목차 · 미배정)에 있는 요구사항
  const mine = draft.requirements.filter((r) => r.section_id === sectionId)
  const others = draft.requirements.filter((r) => r.section_id !== sectionId)
  const sectionTitle = (sid) => draft.sections.find((x) => x.id === sid)?.title
  const assign = (rid, sid) => act(() => api.updateRequirement(draft.id, rid, { section_id: sid }))

  if (pending?.kind === 'outline') return <Working>목차를 새로 제안받는 중입니다. 끝나면 새 목차와 자료가 여기에 보입니다.</Working>
  if (!draft.sections.length) {
    return (
      <Empty>
        <Typography sx={{ color: 'text.primary', fontSize: FONT_SIZES.lg }}>아직 목차가 없습니다</Typography>
        <Typography sx={{ fontSize: FONT_SIZES.md }}>작성 개요 · 요구사항 · 템플릿 · 참고 문서로 목차를 제안받고, 목차마다 사내 문서에서 자료를 모읍니다.</Typography>
        <Button variant="contained" onClick={() => proposeAndCollect()} disabled={!!busy}>목차 제안받고 자료 모으기</Button>
      </Empty>
    )
  }

  return (
    <Box sx={{ display: 'flex', gap: 1.5, flex: 1, minHeight: 0 }}>
      {/* 목차 목록 */}
      <Card variant="outlined" sx={{ width: 260, flexShrink: 0, p: 2, display: 'flex', flexDirection: 'column' }}>
        <Button size="small" variant="contained" onClick={() => collect(false)} disabled={!!busy} sx={{ mb: 1 }}>모든 목차 자료 모으기</Button>
        <Box component="form" onSubmit={addSection} sx={{ display: 'flex', gap: 0.5, pb: 1, mb: 1, borderBottom: 1, borderColor: 'divider' }}>
          <TextField size="small" fullWidth value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="목차 추가" disabled={!!busy} />
          <IconButton type="submit" size="small" disabled={!newTitle.trim() || !!busy}><AddIcon fontSize="small" /></IconButton>
        </Box>
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          {draft.sections.map((s, i) => {
            const active = s.id === sectionId
            return (
              <Box key={s.id} onClick={() => setSectionId(s.id)} sx={{ p: 1, mb: 0.5, borderRadius: 1.5, cursor: 'pointer', border: 1, borderColor: active ? 'primary.main' : 'transparent', backgroundColor: active ? 'action.selected' : 'transparent', '&:hover': { backgroundColor: 'action.hover' } }}>
                <Typography noWrap sx={{ fontSize: FONT_SIZES.md, fontWeight: 500 }}>{valuesOf(s).title || s.title}</Typography>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {isCollecting(s.id)
                    ? <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'primary.main', flex: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}><CircularProgress size={10} />모으는 중…</Typography>
                    : <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', flex: 1 }}>선택 {s.selected_count} / 후보 {s.source_count}{s.requirement_count ? ` · 요구 ${s.requirement_count}` : ''}</Typography>}
                  {active && (
                    <Box onClick={(e) => e.stopPropagation()} sx={{ display: 'flex' }}>
                      <IconButton size="small" sx={{ p: 0.25 }} onClick={() => move(-1)} disabled={i === 0}><UpIcon sx={{ fontSize: 16 }} /></IconButton>
                      <IconButton size="small" sx={{ p: 0.25 }} onClick={() => move(1)} disabled={i === draft.sections.length - 1}><DownIcon sx={{ fontSize: 16 }} /></IconButton>
                      <IconButton size="small" sx={{ p: 0.25 }} onClick={removeSection}><DeleteIcon sx={{ fontSize: 16 }} /></IconButton>
                    </Box>
                  )}
                </Box>
              </Box>
            )
          })}
        </Box>
        <Button size="small" variant="outlined" sx={{ mt: 1 }} disabled={!!busy}
          onClick={() => window.confirm('요구사항 · 템플릿 · 참고 문서로 목차를 새로 제안받을까요? 지금 목차와 고르지 않은 후보 · 만든 본문은 지워지고, 고른 자료는 가장 가까운 새 목차로 옮겨집니다.') && proposeAndCollect(true)}>
          목차 다시 제안받기
        </Button>
      </Card>

      {/* 목차 설정 (제목 · 작성 지침) + 참고 자료 (찾을 내용 · 요구사항 → 모은 자료) */}
      <Card variant="outlined" sx={{ flex: 1, minWidth: 0, p: 1.5, display: 'flex', flexDirection: 'column' }}>
        {section && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, mt: 1, mb: 2, flexShrink: 0 }}>
            <TextField size="small" fullWidth label="목차 제목" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <TextField size="small" fullWidth label="작성 지침" value={form.guide} onChange={(e) => setForm({ ...form, guide: e.target.value })} multiline rows={3} />
          </Box>
        )}
        {/* 자료 모으기에 영향을 주는 것(찾을 내용 · 요구사항)과 그 결과(모은 자료)를 한 카드로 묶는다 */}
        <Typography sx={{ fontWeight: 600, mb: 0.75, flexShrink: 0 }}>참고 자료</Typography>
        <Card variant="outlined" sx={{ flex: 1, minHeight: 0, p: 1.5, display: 'flex', flexDirection: 'column', backgroundColor: 'background.default' }}>
          {section && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mt: 0.75, mb: 1.5, flexShrink: 0 }}>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <TextField size="small" fullWidth label="찾을 내용" value={form.query} onChange={(e) => setForm({ ...form, query: e.target.value })} />
                <Button size="small" variant="outlined" onClick={() => collect(true)} disabled={!!busy} sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}>다시 모으기</Button>
              </Box>
              {draft.requirements.length > 0 && (
                <Box>
                  <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', mb: 0.75 }}>요구사항 {mine.length}건 — 앞 3건이 검색어에 들어갑니다</Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, alignItems: 'center' }}>
                    {mine.map((r) => (
                      <Tooltip key={r.id} title={r.content}>
                        <Chip size="small" variant="outlined" onDelete={() => assign(r.id, null)}
                          label={<>{r.code && <Box component="span" sx={{ fontFamily: MONO_FONT, mr: 0.75, color: 'text.secondary' }}>{r.code}</Box>}{r.content}</>}
                          sx={{ maxWidth: 360, fontSize: FONT_SIZES.xs }} />
                      </Tooltip>
                    ))}
                    {others.length > 0 && (
                      <Select size="small" value="" displayEmpty onChange={(e) => e.target.value && assign(e.target.value, sectionId)}
                        renderValue={() => <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>+ 요구사항 붙이기</Typography>}
                        sx={{ height: 24, '& .MuiSelect-select': { py: 0 } }} MenuProps={{ slotProps: { paper: { sx: { maxHeight: 360, maxWidth: 560 } } } }}>
                        {others.map((r) => (
                          <MenuItem key={r.id} value={r.id} sx={{ display: 'block', whiteSpace: 'normal' }}>
                            <Typography sx={{ fontSize: FONT_SIZES.sm }}>{r.code ? `${r.code} ` : ''}{r.content}</Typography>
                            <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{r.section_id ? `지금: ${sectionTitle(r.section_id)}` : '아직 목차에 붙지 않음'}</Typography>
                          </MenuItem>
                        ))}
                      </Select>
                    )}
                  </Box>
                </Box>
              )}
            </Box>
          )}
          <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', mb: 1, flexShrink: 0 }}>찾을 내용과 요구사항으로 사내 문서와 올린 참고 문서에서 찾아 모은 자료입니다. 체크한 자료만 본문 작성에 사용합니다. 다시 모으면 체크하지 않은 자동 후보만 바뀌고, 체크한 자료는 남습니다. 📌 는 반드시 참고 — 자료가 많아 잘릴 때도 가장 먼저 넣습니다.</Typography>
          <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
            {collectingHere ? <Working>이 목차의 자료를 모으는 중입니다…</Working>
              : loading ? <Empty><CircularProgress size={18} /></Empty>
              : sources.length === 0 ? <Empty>후보가 없습니다. [다시 모으기] 를 누르세요.</Empty>
              : sources.map((s) => (
                <Box key={s.id} onClick={() => setPreview(s)} sx={{ display: 'flex', gap: 0.5, alignItems: 'flex-start', p: 0.75, mb: 0.5, borderRadius: 1.5, border: 1, cursor: 'pointer', borderColor: preview?.id === s.id ? 'primary.main' : 'divider', backgroundColor: s.selected ? '#f8fbff' : 'transparent' }}>
                  <Checkbox size="small" checked={s.selected} onClick={(e) => e.stopPropagation()} onChange={(e) => toggle(s, { selected: e.target.checked })} sx={{ p: 0.5 }} />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
                      <Typography noWrap sx={{ fontWeight: 500, fontSize: FONT_SIZES.md, minWidth: 0 }}>{s.title}</Typography>
                      {s.kind === 'reference' && <Tooltip title="올린 참고 문서의 부분입니다 (컨플루언스에 없는 내용)"><Chip size="small" label="참고 문서" sx={{ height: 20, fontSize: FONT_SIZES.xs, backgroundColor: '#eef2ff', color: '#4338ca' }} /></Tooltip>}
                    {s.origin === 'manual' && <Chip size="small" label="직접 추가" sx={{ height: 20, fontSize: FONT_SIZES.xs }} />}
                      {s.source_state === 'changed' && <Tooltip title="고른 뒤 원문이 수정됐습니다. 다시 모으거나 원문을 확인하세요"><Chip size="small" label="원문 수정됨" sx={{ height: 20, fontSize: FONT_SIZES.xs, backgroundColor: '#fffbeb', color: '#b45309' }} /></Tooltip>}
                      {s.source_state === 'deleted' && <Chip size="small" label="원문 삭제됨" sx={{ height: 20, fontSize: FONT_SIZES.xs, backgroundColor: '#fef2f2', color: '#dc2626' }} />}
                      {s.score != null && <Typography sx={{ ml: 'auto', flexShrink: 0, fontFamily: MONO_FONT, fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{Math.round(s.score * 100)}%</Typography>}
                    </Box>
                    <ShortPath path={s.path} heading={s.chunk_ordinal == null ? '문서 전체' : s.heading} />
                  </Box>
                  <Tooltip title={s.pinned ? '고정 해제' : '반드시 참고 (자료가 많아 잘릴 때도 가장 먼저 넣습니다)'}>
                    <IconButton size="small" onClick={(e) => { e.stopPropagation(); toggle(s, { pinned: !s.pinned }) }}>{s.pinned ? <PinIcon fontSize="small" color="primary" /> : <PinOutlinedIcon fontSize="small" />}</IconButton>
                  </Tooltip>
                  <IconButton size="small" onClick={(e) => { e.stopPropagation(); remove(s) }}><DeleteIcon fontSize="small" /></IconButton>
                </Box>
              ))}
          </Box>
        </Card>
      </Card>

      {/* 미리보기 */}
      <Card variant="outlined" sx={{ width: '32%', minWidth: 280, flexShrink: 0, p: 1.5, display: 'flex', flexDirection: 'column' }}>
        {preview ? (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
              <Typography variant="h6" noWrap sx={{ minWidth: 0 }}>{preview.title}</Typography>
              {preview.url && <IconButton size="small" href={preview.url} target="_blank" rel="noreferrer" sx={{ ml: 'auto' }}><OpenInNewIcon fontSize="small" /></IconButton>}
            </Box>
            <Breadcrumb path={preview.path} heading={preview.heading} />
            <Box sx={{ mt: 1, flex: 1, overflow: 'auto', whiteSpace: 'pre-wrap', fontSize: FONT_SIZES.sm, lineHeight: 1.7, backgroundColor: 'background.default', border: 1, borderColor: 'divider', borderRadius: 1, p: 1.25 }}>{preview.content}</Box>
          </>
        ) : <Empty>자료를 누르면 고른 시점의 내용 사본이 여기에 보입니다.</Empty>}
      </Card>
    </Box>
  )
}

// ───────── 템플릿 · 참고 문서 (선택) — 목차를 만들기 전에 올린다. 목차 제안 때 요구사항과 함께 쓴다 ─────────
// files: [{ id, name, meta }] · max: 올릴 수 있는 개수 (1 이면 [바꾸기], 여러 개면 목록 + [추가])
function UploadSlot({ title, desc, accept, files, max, onUpload, onRemove, disabled }) {
  const ref = useRef(null)
  const single = max === 1
  const full = files.length >= max
  const kinds = accept.replaceAll('.', '').replaceAll(',', ' · ')
  return (
    <Card variant="outlined" sx={{ p: 2, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', backgroundColor: files.length ? '#f8fbff' : 'transparent' }}>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mb: 0.5 }}>
        <Typography sx={{ fontWeight: 600 }}>{title}</Typography>
        {!single && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{files.length} / {max}</Typography>}
      </Box>
      <Hint>{desc}</Hint>
      <input ref={ref} type="file" hidden accept={accept} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onUpload(f) }} />
      {files.map((f) => (
        <Box key={f.id} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.75, borderTop: 1, borderColor: 'divider' }}>
          <FileIcon fontSize="small" sx={{ color: 'text.secondary' }} />
          <Typography noWrap sx={{ flex: 1, minWidth: 0, fontSize: FONT_SIZES.md }}>{f.name}</Typography>
          {f.meta && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', flexShrink: 0 }}>{f.meta}</Typography>}
          {single && <Button size="small" variant="outlined" startIcon={<UploadIcon />} onClick={() => ref.current?.click()} disabled={disabled}>바꾸기</Button>}
          <Button size="small" variant="outlined" color="error" onClick={() => onRemove(f.id)} disabled={disabled}>삭제</Button>
        </Box>
      ))}
      {!full && (
        <Box sx={{ mt: 1 }}>
          <Button variant={files.length ? 'outlined' : 'contained'} size="small" startIcon={<UploadIcon />} onClick={() => ref.current?.click()} disabled={disabled}>
            {files.length ? '파일 추가' : '파일 올리기'} ({kinds})
          </Button>
        </Box>
      )}
      {!single && full && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', mt: 1 }}>최대 {max}개까지 올릴 수 있습니다. 바꾸려면 하나를 지우세요.</Typography>}
    </Card>
  )
}

function TemplateStep({ draft, setDraft, busy, setBusy, setError, notify }) {
  const fmt = draft.doc_format
  // 이미 목차가 있으면(뒤로 돌아와 바꾼 경우) 목차에는 바로 반영하지 않으므로 다시 제안받으라고 알린다
  const after = draft.sections.length ? ' 지금 목차에 반영하려면 목차 · 자료 선별에서 [목차 다시 제안받기] 를 누르세요.' : ' 다음 단계에서 목차를 만들 때 함께 참고합니다.'
  const afterRef = draft.sections.length ? ' 자료 후보에 넣으려면 목차 · 자료 선별에서 [모든 목차 자료 모으기] 를 누르세요.' : ' 다음 단계에서 자료를 모을 때 사내 문서와 함께 찾습니다.'
  const run = async (msg, fn, done) => {
    setBusy(msg)
    try { setDraft(await fn()); notify(done) } catch (e) { setError(e.message) } finally { setBusy('') }
  }
  const confirmRemove = (what) => window.confirm(`${what}을 지울까요? 지금 목차 · 자료 · 본문은 그대로 둡니다.`)

  return (
    <Box sx={{ display: 'flex', gap: 2, pt: 1, alignItems: 'flex-start' }}>
      <UploadSlot title="템플릿" accept={`.${fmt}`} max={1} disabled={!!busy}
        files={draft.template_form ? [{ id: 'form', name: draft.template_form }] : []}
        onUpload={(f) => run('템플릿을 읽는 중…', () => api.uploadTemplate(draft.id, f), `템플릿을 올렸습니다.${after}`)}
        onRemove={() => confirmRemove('템플릿') && run('템플릿을 지우는 중…', () => api.removeTemplate(draft.id), '템플릿을 지웠습니다.')}
        desc={<>회사에서 쓰는 {fmt} 파일에 본문이 들어갈 자리를 <b>{'{{개요}}'}</b> 처럼 표시해 올리세요. 자리 표시마다 목차가 되고, 내보낼 때 그 자리에 본문이 들어갑니다. <b>{'{{문서명}} {{작성일}}'}</b> 은 자동으로 채워집니다.</>} />
      <UploadSlot title="참고 문서" accept=".docx,.pptx,.pdf,.md,.txt" max={5} disabled={!!busy}
        files={(draft.references || []).map((r) => ({ id: r.id, name: r.file_name, meta: `${r.chars.toLocaleString()}자` }))}
        onUpload={(f) => run(`${f.name} 을 읽고 소제목별로 나누는 중…`, () => api.uploadReference(draft.id, f), `참고 문서를 올렸습니다.${afterRef}`)}
        onRemove={(rid) => window.confirm('참고 문서를 지울까요? 이 문서에서 모은 자료 후보도 함께 지워집니다.') && run('참고 문서를 지우는 중…', () => api.removeReference(draft.id, rid), '참고 문서를 지웠습니다.')}
        desc="컨플루언스에 없는 내용을 담은 문서를 최대 5개까지 올리세요. 자료를 모을 때 사내 문서와 함께 목차마다 관련 부분을 찾아 후보로 넣고, 체크한 부분은 본문을 쓸 때 내용의 근거로 씁니다." />
    </Box>
  )
}

// ───────── 작성 · 검토 ─────────
function SectionCard({ draft, s, onGenerate, state, open, onToggle, setDraft, setError }) {
  const generating = state === 'running'
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(s.body || '')
  const reqs = draft.requirements.filter((r) => r.section_id === s.id)
  const missing = reqs.filter((r) => r.covered === false).length
  const unsure = ((s.body || '').match(/\[확인 필요/g) || []).length
  useEffect(() => { if (!editing) setBody(s.body || '') }, [s.body, editing])

  const save = async () => {
    try { setDraft(await api.updateDraftSection(draft.id, s.id, { body })); setEditing(false) } catch (e) { setError(e.message) }
  }

  return (
    <Card variant="outlined" sx={{ px: 2, py: 1.5, mb: 1.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <IconButton size="small" onClick={onToggle} sx={{ ml: -0.75, transform: open ? 'rotate(0deg)' : 'rotate(-90deg)', transition: 'transform .15s' }}><ExpandIcon /></IconButton>
        <Typography variant="h6" onClick={onToggle} sx={{ cursor: 'pointer' }}>{s.title}</Typography>
        {s.version > 0 && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>v{s.version} · {fmtTime(s.generated_at)}</Typography>}
        <Typography sx={{ fontSize: FONT_SIZES.xs, color: s.selected_count ? 'text.secondary' : '#b45309' }}>참고 자료 {s.selected_count}건</Typography>
        {/* 접었을 때도 검토할 것이 남았는지 보이게 한다 */}
        {!open && missing > 0 && <Chip size="small" icon={<CrossIcon />} color="error" variant="outlined" label={`요구사항 누락 ${missing}`} sx={{ height: 22, fontSize: FONT_SIZES.xs }} />}
        {!open && unsure > 0 && <Chip size="small" icon={<WarnIcon />} color="warning" variant="outlined" label={`확인 필요 ${unsure}`} sx={{ height: 22, fontSize: FONT_SIZES.xs }} />}
        <Box sx={{ ml: 'auto', display: 'flex', gap: 1 }}>
          {s.body && !editing && <Button size="small" variant="outlined" onClick={() => setEditing(true)}>직접 고치기</Button>}
          {editing && <><Button size="small" variant="outlined" onClick={() => setEditing(false)}>취소</Button><Button size="small" variant="contained" onClick={save}>저장</Button></>}
          {!editing && <Button size="small" variant={s.body ? 'outlined' : 'contained'} onClick={onGenerate} disabled={!!state}>{generating ? <><CircularProgress size={14} sx={{ mr: 0.5 }} />작성 중</> : state === 'waiting' ? '대기 중' : s.body ? '다시 생성' : '생성'}</Button>}
        </Box>
      </Box>
      <Collapse in={open} unmountOnExit>
      <Box sx={{ pt: 1 }}>
      {reqs.length > 0 && (
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1 }}>
          {reqs.map((r) => (
            <Tooltip key={r.id} title={<>{r.content}{r.coverage_note && <><br /><br />{r.coverage_note}</>}</>}>
              <Chip size="small" variant="outlined" icon={r.covered == null ? undefined : <CoverageIcon covered={r.covered} />} label={r.code || r.content.slice(0, 18) + '…'} sx={{ fontSize: FONT_SIZES.xs }} />
            </Tooltip>
          ))}
        </Box>
      )}
      {state === 'running' ? <Working>이 목차를 작성하는 중입니다…</Working>
        : state === 'waiting' ? <Typography sx={{ color: 'text.disabled', fontSize: FONT_SIZES.md, py: 1 }}>앞 목차가 끝나면 다시 작성합니다.</Typography>
        : editing
        ? <TextField fullWidth multiline minRows={10} value={body} onChange={(e) => setBody(e.target.value)} sx={{ '& textarea': { fontFamily: MONO_FONT, fontSize: FONT_SIZES.sm } }} />
        : s.body
          ? (
            <Box sx={{ lineHeight: 1.7, fontSize: FONT_SIZES.lg, '& > :first-of-type': { mt: 0 }, '& table': { borderCollapse: 'collapse', my: 1 }, '& th, & td': { border: 1, borderColor: 'divider', px: 1, py: 0.5, fontSize: FONT_SIZES.md } }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.body.replace(/[ \t]?(\[\d+\])+/g, '').replace(/\[확인 필요([^\]]*)\]/g, '**⚠ 확인 필요$1**')}</ReactMarkdown>
            </Box>
          )
          : <Typography sx={{ color: 'text.disabled', fontSize: FONT_SIZES.md }}>아직 생성하지 않았습니다.</Typography>}
      {s.citations.length > 0 && !editing && !state && (
        // 작성본에는 출처를 달지 않는다. 검토용으로 이 목차를 쓸 때 넣은 자료만 보여 준다 (내보내기에는 들어가지 않음)
        <Box sx={{ mt: 1, pt: 1, borderTop: 1, borderColor: 'divider' }}>
          <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', fontWeight: 600, mb: 0.25 }}>참고 자료</Typography>
          {s.citations.map((c) => (
            <Typography key={c.n} sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>
              · {c.url ? <Link href={c.url} target="_blank" rel="noreferrer">{c.title}</Link> : c.title}{c.heading ? ` · ${c.heading}` : ''}
            </Typography>
          ))}
        </Box>
      )}
      </Box>
      </Collapse>
    </Card>
  )
}

function WriteTab({ draft, setDraft, setError, notify }) {
  const [running, setRunning] = useState(null) // 생성 중인 목차 id
  const [waiting, setWaiting] = useState([]) // 차례를 기다리는 목차 id (다시 생성 대상은 화면에서 비워 둔다)
  const [progress, setProgress] = useState(null) // { done, total }
  const [exporting, setExporting] = useState(false)
  const [closed, setClosed] = useState({}) // 접힌 카드

  const genOne = async (sid) => {
    setRunning(sid); setWaiting((w) => w.filter((x) => x !== sid))
    try { setDraft(await api.generateSection(draft.id, sid)) } catch (e) { setError(e.message); throw e } finally { setRunning(null) }
  }
  // 앞 목차 결과가 다음 목차 프롬프트(앞 목차 요약)에 들어가므로 순서대로 하나씩 만든다
  const genAll = async (onlyEmpty) => {
    const targets = draft.sections.filter((s) => !onlyEmpty || !s.body)
    setWaiting(targets.map((s) => s.id))
    setProgress({ done: 0, total: targets.length })
    try {
      for (let i = 0; i < targets.length; i++) {
        await genOne(targets[i].id)
        setProgress({ done: i + 1, total: targets.length })
      }
      notify(`목차 ${targets.length}개를 작성했습니다.`)
    } catch { /* 오류는 위에서 표시 */ } finally { setProgress(null); setWaiting([]) }
  }
  const allClosed = draft.sections.length > 0 && draft.sections.every((s) => closed[s.id])
  const toggleAll = () => setClosed(allClosed ? {} : Object.fromEntries(draft.sections.map((s) => [s.id, true])))
  const doExport = async () => {
    setExporting(true)
    try { await api.exportDraft(draft.id, draft.name) } catch (e) { setError(e.message) } finally { setExporting(false) }
  }
  const uncovered = draft.requirements.filter((r) => r.covered === false)
  const unassigned = draft.requirements.filter((r) => !r.section_id)
  const empty = draft.sections.filter((s) => !s.body).length

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 1 }}>
        <Button size="small" variant="contained" onClick={() => genAll(true)} disabled={!!running || !empty}>빈 목차 모두 생성 ({empty})</Button>
        <Button size="small" variant="outlined" onClick={() => window.confirm('모든 목차를 다시 생성할까요? 직접 고친 내용도 덮어씁니다.') && genAll(false)} disabled={!!running}>전체 다시 생성</Button>
        <Button size="small" variant="outlined" onClick={toggleAll}>{allClosed ? '모두 펼치기' : '모두 접기'}</Button>
        {(uncovered.length > 0 || unassigned.length > 0) && (
          <Tooltip title={<>
            {uncovered.length > 0 && <div>본문에 빠진 요구사항: {uncovered.map((r) => r.code || r.content.slice(0, 15)).join(', ')}</div>}
            {unassigned.length > 0 && <div>목차에 배정되지 않은 요구사항 {unassigned.length}건은 본문에 반영되지 않습니다.</div>}
          </>}>
            <Chip icon={<WarnIcon fontSize="small" />} color="warning" variant="outlined"
              sx={{ height: 34, borderRadius: '6px', fontSize: '0.875rem', fontWeight: 600, '& .MuiChip-label': { px: 1.5, pl: 0.75 }, '& .MuiChip-icon': { ml: 1.25 } }} label={`요구사항 ${uncovered.length ? `누락 ${uncovered.length}` : ''}${uncovered.length && unassigned.length ? ' · ' : ''}${unassigned.length ? `미배정 ${unassigned.length}` : ''}`} />
          </Tooltip>
        )}
        <Box sx={{ flex: 1 }} />
        {draft.template_form && <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>템플릿({draft.template_form})에 채워 {draft.doc_format} 로 내보냅니다</Typography>}
        <Button size="small" variant="contained" startIcon={exporting ? <CircularProgress size={14} color="inherit" /> : <DownloadIcon />} onClick={doExport} disabled={exporting || !!running}>내보내기</Button>
      </Box>
      {/* 진행 막대는 높이를 미리 잡아 두어 화면이 밀리지 않게 한다 */}
      <Box sx={{ height: 4, mb: 1 }}>{progress && <LinearProgress variant="determinate" value={(progress.done / Math.max(progress.total, 1)) * 100} />}</Box>
      <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary', mb: 1 }}>
        {progress ? `${progress.done} / ${progress.total} 목차 작성 중 · ` : ''}근거가 없는 내용은 <b>⚠ 확인 필요</b> 로 표시됩니다. 내보내기 전에 수정해주세요.
      </Typography>
      <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, pr: 0.5 }}>
        {draft.sections.map((s) => (
          <SectionCard key={s.id} draft={draft} s={s} onGenerate={() => genOne(s.id).catch(() => {})}
            state={running === s.id ? 'running' : waiting.includes(s.id) ? 'waiting' : null}
            open={!closed[s.id]} onToggle={() => setClosed((c) => ({ ...c, [s.id]: !c[s.id] }))} setDraft={setDraft} setError={setError} />
        ))}
      </Box>
    </Box>
  )
}

// ───────── 작성 다이얼로그 (단계: 기본 정보 → 요구사항 → 자료 선별 → 템플릿 → 작성 · 검토) ─────────
const STEPS = ['기본 정보', '요구사항', '템플릿 · 참고 문서', '목차 · 자료 선별', '작성 · 검토']

// 기존 작성 건을 열 때 이어서 할 단계
const resumeStep = (d) => (d.sections.some((s) => s.body) ? 4 : d.sections.length ? 3 : 1)

export default function DraftDialog({ open, draftId, space, onClose, onChanged }) {
  const [draft, setDraft] = useState(null)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState(null) // { severity, msg } — 화면이 밀리지 않도록 알림은 토스트로
  const [pending, setPending] = useState(null) // { kind: 'outline' } | { kind: 'collect', sectionId } — 다시 만드는 대상은 화면에서 비워 둔다
  const setError = useCallback((msg) => { if (msg) setToast({ severity: 'error', msg }) }, [])
  const notify = useCallback((msg) => setToast({ severity: 'success', msg }), [])
  const [name, setName] = useState('')
  const [overview, setOverview] = useState('')
  const [docFormat, setDocFormat] = useState('docx')
  const [loading, setLoading] = useState(false)
  const flushRef = useRef(null) // 목차 · 자료 선별 화면의 { save: 고친 내용 저장, dirty: 저장 안 된 수정이 있는지 }

  useEffect(() => {
    if (!open) return
    setToast(null); setBusy(''); setPending(null)
    if (!draftId) { setDraft(null); setName(''); setOverview(''); setDocFormat('docx'); setStep(0); return }
    setLoading(true)
    api.getDraft(draftId).then((d) => { setDraft(d); setName(d.name); setOverview(d.overview); setDocFormat(d.doc_format || 'docx'); setStep(resumeStep(d)) })
      .catch((e) => setError(e.message)).finally(() => setLoading(false))
  }, [open, draftId])

  const reload = useCallback(async () => {
    if (!draft) return
    try { setDraft(await api.getDraft(draft.id)) } catch (e) { setError(e.message) }
  }, [draft?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const update = (d) => { setDraft(d); onChanged?.() }

  // 기본 정보 저장 — 새 건이면 여기서 만든다
  const saveInfo = async () => {
    if (!draft) { const d = await api.createDraft(name.trim(), overview.trim(), docFormat); update(d); return d }
    if (name.trim() !== draft.name || overview !== draft.overview || docFormat !== draft.doc_format) {
      const d = await api.updateDraft(draft.id, { name: name.trim(), overview, doc_format: docFormat }); update(d); return d
    }
    return draft
  }
  // 목차 제안 → 모든 목차 자료 모으기
  const proposeAndCollect = async (replace = false) => {
    try {
      setBusy('요구사항 · 템플릿 · 참고 문서를 보고 목차를 제안받는 중…'); setPending({ kind: 'outline' })
      const d = await api.proposeOutline(draft.id, replace)
      update(d)
      setBusy('목차마다 사내 문서에서 자료를 모으는 중…'); setPending({ kind: 'collect', sectionId: null })
      update(await api.collectSources(draft.id, null, space))
      notify(`목차 ${d.sections.length}개를 제안받고 자료를 모았습니다.`)
    } catch (e) { setError(e.message) } finally { setBusy(''); setPending(null) }
  }
  // 단계를 옮길 때 지금 화면에서 고친 내용을 저장한다
  const goto = async (next) => {
    try {
      if (step === 0) await saveInfo()
      if (step === 3 && flushRef.current) await flushRef.current.save()
      flushRef.current = null
      setStep(next)
    } catch (e) { setError(e.message) }
  }
  // 닫기는 저장하지 않는다 (저장은 단계를 옮길 때만). 저장 안 된 수정이 있으면 버릴지 묻는다
  const close = () => {
    if (flushRef.current?.dirty && !window.confirm('저장되지 않은 수정이 있습니다. 저장하지 않고 닫을까요?')) return
    flushRef.current = null
    onClose()
  }
  // 목차 · 자료 선별로 처음 넘어갈 때 목차가 비어 있으면 바로 제안받는다 (요구사항 · 템플릿 · 참고 문서를 함께 본다)
  useEffect(() => { if (open && step === 3 && draft && !draft.sections.length && !busy) proposeAndCollect() }, [step, draft?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const remove = async () => {
    if (!window.confirm(`"${draft.name}" 을 삭제할까요? 모은 자료와 생성 결과가 모두 지워집니다.`)) return
    try { await api.deleteDraft(draft.id); onChanged?.(); onClose() } catch (e) { setError(e.message) }
  }

  const props = { draft, reload, setDraft: update, busy, setBusy, setError, notify, pending, setPending, space }
  const selected = draft ? draft.sections.reduce((a, s) => a + s.selected_count, 0) : 0
  const written = draft ? draft.sections.filter((s) => s.body).length : 0
  const sub = draft ? [
    FORMAT_LABEL[draft.doc_format],
    draft.requirements.length ? `${draft.requirements.length}건` : '없음',
    [draft.template_form && '템플릿 1', draft.references?.length && `참고 ${draft.references.length}`].filter(Boolean).join(' · ') || '없음 (선택)',
    draft.sections.length ? `목차 ${draft.sections.length} · 자료 ${selected}` : '',
    draft.sections.length ? `${written} / ${draft.sections.length}` : '',
  ] : []

  return (
    <Dialog open={open} onClose={() => !busy && close()} fullWidth maxWidth={false}
      slotProps={{ paper: { sx: { width: 'min(1680px, calc(100% - 48px))', height: 'min(1000px, calc(100% - 48px))', maxHeight: 'none', m: 3 } } }}>
      {/* 머리 */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 3, pt: 2, pb: 1.5, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="h6" noWrap sx={{ flex: 1, minWidth: 0 }}>{draft?.name || '새 자료 작성'}</Typography>
        <IconButton size="small" aria-label="닫기" onClick={close} disabled={!!busy} sx={{ ml: 'auto', p: 0.5, position: 'relative', zIndex: 2 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>
      <Box sx={{ px: 3, pt: 2, pb: 2, borderBottom: 1, borderColor: 'divider' }}>
        <Stepper nonLinear activeStep={step} alternativeLabel sx={{ '& .MuiStepLabel-label.MuiStepLabel-alternativeLabel': { mt: 1 } }}>
          {STEPS.map((label, i) => (
            <Step key={label} completed={false} sx={{ display: 'flex', justifyContent: 'center' }}>
              {/* StepButton 기본값은 칸 너비 전체 + 위아래 24px 까지 눌린다. 글자 크기만큼만 눌리게 줄인다 (위로 튀어나와 닫기 버튼을 덮던 문제도 함께) */}
              <StepButton onClick={() => goto(i)} disabled={!draft || !!busy} sx={{ m: 0, mx: 'auto', py: 0.5, px: 1.5, width: 'auto', borderRadius: 1.5 }}
                optional={sub[i] ? <Typography sx={{ fontSize: FONT_SIZES.xs, color: 'text.secondary' }}>{sub[i]}</Typography> : undefined}>
                {label}
              </StepButton>
            </Step>
          ))}
        </Stepper>
      </Box>

      <DialogContent sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, pt: '16px !important' }}>
        {loading ? <Empty><CircularProgress size={20} /></Empty> : (
          <Box sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            {step === 0 && <InfoStep name={name} setName={setName} overview={overview} setOverview={setOverview} docFormat={docFormat} setDocFormat={setDocFormat} formLocked={!!draft?.template_form} />}
            {draft && step === 1 && <RequirementsStep {...props} />}
            {draft && step === 2 && <TemplateStep {...props} />}
            {draft && step === 3 && <SourcesStep key={draft.id} {...props} proposeAndCollect={proposeAndCollect} flushRef={flushRef} />}
            {draft && step === 4 && <WriteTab {...props} />}
          </Box>
        )}
      </DialogContent>

      {/* 가운데: ‹ 이전 ●●●●● 다음 › (붙여서) · 오른쪽: 삭제 */}
      <DialogActions sx={{ px: 3, py: 1.75, borderTop: 1, borderColor: 'divider', display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center' }}>
        <Box />
        <MobileStepper variant="dots" steps={STEPS.length} activeStep={step} position="static"
          sx={{ p: 0, gap: 1, backgroundColor: 'transparent', '& .MuiMobileStepper-dots': { mx: 0.5 } }}
          backButton={<Button size="small" variant="outlined" onClick={() => goto(step - 1)} disabled={step === 0 || !!busy} sx={{ fontWeight: 400, pl: 0.75 }}><PrevIcon fontSize="small" />이전</Button>}
          nextButton={<Button size="small" variant="outlined" onClick={() => goto(step + 1)} disabled={step === STEPS.length - 1 || !!busy || (step === 0 && !name.trim())} sx={{ fontWeight: 400, pr: 0.75 }}>다음<NextIcon fontSize="small" /></Button>} />
        <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
          {draft && <Button color="error" variant="outlined" size="small" onClick={remove} disabled={!!busy}>삭제</Button>}
        </Box>
      </DialogActions>

      {/* 진행 중 (끝날 때까지) · 결과 / 오류 (잠시 뒤 사라짐) */}
      <Snackbar open={!!busy} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        <Alert severity="info" variant="filled" icon={<CircularProgress size={16} color="inherit" />} sx={{ boxShadow: 3 }}>{busy}</Alert>
      </Snackbar>
      <Snackbar open={!!toast} autoHideDuration={toast?.severity === 'error' ? 8000 : 4000} onClose={(_, reason) => reason !== 'clickaway' && setToast(null)}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}>
        {toast ? <Alert severity={toast.severity} variant="filled" onClose={() => setToast(null)} sx={{ boxShadow: 3, maxWidth: 640 }}>{toast.msg}</Alert> : <span />}
      </Snackbar>
    </Dialog>
  )
}
