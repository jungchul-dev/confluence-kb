import React, { useCallback, useEffect, useState } from 'react'
import { Box, Typography, TextField, Button, Card, Alert, Link, Chip, Pagination } from '@mui/material'
import { ResponsiveCirclePacking } from '@nivo/circle-packing'
import { animated, to } from '@react-spring/web'
import * as api from '../api'

const CLUSTER_COLORS = ['#2563eb', '#16a34a', '#dc2626', '#9333ea', '#ea580c', '#0891b2', '#ca8a04', '#be185d',
  '#4f46e5', '#059669', '#db2777', '#7c3aed', '#0d9488', '#c2410c', '#4338ca', '#0284c7']

const PAGE_SIZE = 20
// 차트와 오른쪽 목록의 높이: 브라우저 높이에서 상단 헤더·툴바·여백(약 190px)을 뺀 값. 창 높이를 줄이면 같이 줄어든다
const PANEL_HEIGHT = 'calc(100vh - 190px)'
const PANEL_MIN_HEIGHT = 420

// 대표 문서 제목에서 첨부 파일명(" — 파일명")을 떼고 경로 구분자를 보기 좋게 바꾼다. 잘라내지는 않는다.
const cleanTitle = (title) => title.replace(/\s*—\s*.*$/, '').replace(/\s*>\s*/g, ' › ')

const textColorFor = (hex) => {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#18181b' : '#ffffff'
}

// 글자 폭 근사치 (px): 한글·전각은 fontSize, 영문·숫자는 0.58배, 공백은 0.3배
const charWidth = (ch, fontSize) => {
  const code = ch.charCodeAt(0)
  if (ch === ' ') return fontSize * 0.3
  if (code < 128) return fontSize * 0.58
  return fontSize
}
const textWidth = (s, fontSize) => [...s].reduce((w, ch) => w + charWidth(ch, fontSize), 0)

// 텍스트를 maxWidth 안에 들어가도록 줄바꿈한다. 단어 단위로 자르고, 한 단어가 너무 길면 글자 단위로 자른다.
const wrapText = (text, fontSize, maxWidth, maxLines) => {
  const lines = []
  let line = ''
  const pushWord = (word) => {
    const candidate = line ? `${line} ${word}` : word
    if (textWidth(candidate, fontSize) <= maxWidth) { line = candidate; return }
    if (line) { lines.push(line); line = '' }
    if (textWidth(word, fontSize) <= maxWidth) { line = word; return }
    let piece = ''
    for (const ch of word) {
      if (textWidth(piece + ch, fontSize) > maxWidth) { lines.push(piece); piece = '' }
      piece += ch
    }
    line = piece
  }
  text.split(/\s+/).filter(Boolean).forEach(pushWord)
  if (line) lines.push(line)
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines)
    kept[maxLines - 1] = kept[maxLines - 1].replace(/.$/, '') + '…'
    return kept
  }
  return lines
}

// 원 안에 제목을 여러 줄로, 굵게 표시하는 라벨. 마지막 줄에 문서 수를 둔다.
const CircleLabel = ({ node, style }) => {
  const radius = node.radius
  if (node.depth !== 1 || radius < 14) return null
  const fontSize = Math.max(12, Math.min(19, radius / 4.8))
  const lineHeight = fontSize * 1.2
  const maxWidth = radius * 1.6
  const maxLines = Math.max(1, Math.floor((radius * 1.7) / lineHeight) - 1)
  const titleLines = wrapText(cleanTitle(node.data.title), fontSize, maxWidth, maxLines)
  const lines = [...titleLines, `(${node.data.count}개)`]
  const startY = -((lines.length - 1) * lineHeight) / 2
  // 원과 같은 스프링 값(style.x/y)을 써서 라벨이 원과 함께 움직이게 한다
  return (
    <animated.g
      transform={to([style.x, style.y], (x, y) => `translate(${x},${y})`)}
      opacity={style.opacity}
      style={{ pointerEvents: 'none' }}
    >
      <animated.text
        textAnchor="middle"
        dominantBaseline="central"
        fill={style.textColor}
        style={{ fontSize, fontWeight: 700, fontFamily: 'inherit' }}
      >
        {lines.map((l, i) => (
          <tspan key={i} x={0} y={startY + i * lineHeight} style={i === lines.length - 1 ? { fontWeight: 500, fontSize: fontSize * 0.85, opacity: 0.85 } : undefined}>
            {l}
          </tspan>
        ))}
      </animated.text>
    </animated.g>
  )
}

// 바깥 원(depth 0)에는 툴팁을 띄우지 않는다. 클러스터 원에는 제목과 문서 수만 보여준다.
const ClusterTooltip = (node) => {
  if (node.depth !== 1) return null
  return (
    <div style={{ background: '#fff', border: '1px solid #e4e4e7', borderRadius: 6, padding: '6px 10px', fontSize: 13, boxShadow: '0 4px 12px rgba(0,0,0,0.08)', whiteSpace: 'nowrap' }}>
      <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: node.data.color, marginRight: 6, verticalAlign: 'middle' }} />
      <strong>{cleanTitle(node.data.title)}</strong>
      <span style={{ color: '#71717a', marginLeft: 6 }}>{node.data.count}개 문서</span>
      {node.data.repTitle && <div style={{ color: '#71717a', marginTop: 4, fontSize: 12 }}>대표 문서: {cleanTitle(node.data.repTitle)}</div>}
    </div>
  )
}

export default function AnalyticsView() {
  const [clusters, setClusters] = useState([])
  const [totalDocs, setTotalDocs] = useState(0)
  const [info, setInfo] = useState(null) // { silhouette, docs_without_embedding, k_candidates }
  const [k, setK] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(1)

  useEffect(() => { setPage(1) }, [selected])

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const data = await api.getClusters(k)
      setClusters(data.clusters); setTotalDocs(data.total_documents); setK(data.k)
      setInfo({ silhouette: data.silhouette, docs_without_embedding: data.docs_without_embedding, k_candidates: data.k_candidates || [] })
      setSelected(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [k])

  const bubbleData = {
    id: 'root',
    color: 'transparent',
    children: clusters.map((c, i) => {
      const color = CLUSTER_COLORS[i % CLUSTER_COLORS.length]
      return {
        id: `cluster-${c.cluster_id}`,
        title: c.label || (c.representative_docs[0] ? c.representative_docs[0].title : `클러스터 ${c.cluster_id}`),
        repTitle: c.representative_docs[0] ? c.representative_docs[0].title : '',
        count: c.doc_count,
        value: c.doc_count,
        color,
        textColor: textColorFor(color),
        cluster: c,
      }
    }),
  }

  const selectedDocs = selected ? (selected.all_docs || selected.representative_docs) : []
  const pageCount = Math.max(1, Math.ceil(selectedDocs.length / PAGE_SIZE))
  const pageDocs = selectedDocs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const selectedColor = selected ? CLUSTER_COLORS[clusters.findIndex(c => c.cluster_id === selected.cluster_id) % CLUSTER_COLORS.length] : undefined

  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }}>
        <Typography color="text.secondary">클러스터 수</Typography>
        <TextField type="number" size="small" sx={{ width: 70 }} slotProps={{ htmlInput: { min: 0, max: 50 } }} value={k} onChange={(e) => setK(Number(e.target.value))} />
        <Button variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} onClick={load} disabled={loading}>{loading ? '분석 중…' : '분석'}</Button>
        <Typography color="text.secondary">(0 = 자동)</Typography>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Typography color="text.secondary" sx={{ mb: 2 }}>
        전체 문서 {totalDocs}개 · 클러스터 {clusters.length}개
        {info?.silhouette != null && ` · 실루엣 ${info.silhouette.toFixed(3)}`}
        {info?.docs_without_embedding > 0 && ` · 문서 임베딩 없음 ${info.docs_without_embedding}개 (청크 평균으로 대체)`}
      </Typography>

      {clusters.length > 0 && (
        <Box sx={{ display: 'flex', gap: 2 }}>
          {/* 버블 차트 */}
          <Box sx={{ height: PANEL_HEIGHT, minHeight: PANEL_MIN_HEIGHT, flex: 1, minWidth: 0 }}>
            <ResponsiveCirclePacking
              data={bubbleData}
              margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
              padding={10}
              colors={({ data }) => data.color || '#e4e4e7'}
              colorBy="id"
              enableLabels
              label={({ data }) => data.title || ''}
              labelTextColor={({ data }) => data.textColor || '#18181b'}
              labelsSkipRadius={14}
              labelComponent={CircleLabel}
              tooltip={ClusterTooltip}
              borderWidth={2}
              borderColor={{ from: 'color', modifiers: [['darker', 0.3]] }}
              onClick={(node) => {
                if (node.depth === 1) setSelected(node.data.cluster)
              }}
              motionConfig="slow"
            />
          </Box>

          {/* 선택된 클러스터 상세 */}
          {selected && (
            <Card variant="outlined" sx={{ p: 2, width: '48%', minWidth: 560, maxWidth: 900, flexShrink: 0, height: PANEL_HEIGHT, minHeight: PANEL_MIN_HEIGHT, boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5, flexWrap: 'wrap' }}>
                <Chip size="small" label={selected.label || `클러스터 ${selected.cluster_id}`} sx={{ backgroundColor: selectedColor, color: '#fff', fontWeight: 600, maxWidth: '100%' }} />
                <Typography color="text.secondary">{selected.doc_count}개 문서</Typography>
                {pageCount > 1 && <Typography color="text.secondary" sx={{ ml: 'auto', fontSize: '0.8125rem' }}>{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, selectedDocs.length)} / {selectedDocs.length}</Typography>}
              </Box>
              {selected.keywords?.length > 0 && (
                <Typography color="text.secondary" sx={{ fontSize: '0.8125rem', mb: 1 }}>
                  {selected.label_source === 'keywords' && <>(LLM 제목 실패, 키워드 제목 사용) · </>}키워드: {selected.keywords.join(', ')}
                  {selected.representative_docs[0] && <> · 대표 문서: {cleanTitle(selected.representative_docs[0].title)}</>}
                </Typography>
              )}
              <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                {pageDocs.map((d) => (
                  <Box key={d.document_id} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.75, borderTop: 1, borderColor: 'divider', fontSize: '0.8125rem', '&:first-of-type': { borderTop: 0 } }}>
                    <Chip size="small" label={d.kind === 'attachment' ? '첨부' : '페이지'} color={d.kind === 'attachment' ? 'success' : 'primary'} variant="filled" sx={{ flexShrink: 0 }} />
                    <Link href={d.url} target="_blank" rel="noreferrer" sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>{d.title}</Link>
                    {d.space_key && <Typography color="text.secondary" sx={{ ml: 'auto', fontSize: '0.75rem', flexShrink: 0 }}>{d.space_key}</Typography>}
                  </Box>
                ))}
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', pt: 1.5, mt: 1, borderTop: 1, borderColor: 'divider', minHeight: 44 }}>
                {pageCount > 1
                  ? <Pagination count={pageCount} page={page} onChange={(_, p) => setPage(p)} size="small" color="primary" showFirstButton showLastButton />
                  : <Typography color="text.secondary" sx={{ fontSize: '0.8125rem' }}>전체 {selectedDocs.length}건</Typography>}
              </Box>
            </Card>
          )}
        </Box>
      )}

      {!loading && clusters.length === 0 && !error && (
        <Box sx={{ textAlign: 'center', py: 5, color: 'text.secondary' }}>문서가 2개 이상일 때 클러스터링 결과가 표시됩니다.</Box>
      )}
    </Box>
  )
}
