import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { forceSimulation, forceX, forceY, forceCollide } from 'd3-force'
import { FONT_SIZES } from '../theme'

// ── 라벨 줄바꿈 (글자 폭 근사: 한글 1em, 영문 0.58em, 공백 0.3em) ──────────────
const charWidth = (ch, fs) => (ch === ' ' ? fs * 0.3 : ch.charCodeAt(0) < 128 ? fs * 0.58 : fs)
const textWidth = (s, fs) => [...s].reduce((w, ch) => w + charWidth(ch, fs), 0)
const wrapText = (text, fs, maxWidth, maxLines) => {
  const lines = []; let line = ''
  const push = (word) => {
    const cand = line ? `${line} ${word}` : word
    if (textWidth(cand, fs) <= maxWidth) { line = cand; return }
    if (line) { lines.push(line); line = '' }
    if (textWidth(word, fs) <= maxWidth) { line = word; return }
    let piece = ''
    for (const ch of word) { if (textWidth(piece + ch, fs) > maxWidth) { lines.push(piece); piece = '' } piece += ch }
    line = piece
  }
  text.split(/\s+/).filter(Boolean).forEach(push)
  if (line) lines.push(line)
  if (lines.length > maxLines) { const kept = lines.slice(0, maxLines); kept[maxLines - 1] = kept[maxLines - 1].replace(/.$/, '') + '…'; return kept }
  return lines
}

// 원이 커지는 배율. 가두는 여백(bound)은 둘 다 적용됐을 때(선택된 원에 오버)를 기준으로 잡아야 잘리지 않는다
const HOVER_SCALE = 1.04
const SELECT_SCALE = 1.06
const MAX_SCALE = HOVER_SCALE * SELECT_SCALE
const EDGE_PAD = 4 // 선택 테두리(2px) 절반 + 여유

/**
 * 떠다니는 버블 차트. items: [{ id, label, count, color, textColor, tooltip }]
 * - 원 크기는 count 에 비례(면적 기준), 전체가 컨테이너의 약 절반을 차지하도록 맞춘다
 * - d3-force 로 서로 겹치지 않게 밀어내고, 느린 사인파 힘을 계속 줘서 가볍게 떠다닌다
 * - 클릭 → onSelect(item), 마우스 오버 → tooltip 표시
 */
export default function FloatingBubbles({ items, selectedId, onSelect }) {
  const wrapRef = useRef(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [nodes, setNodes] = useState([])
  const [hover, setHover] = useState(null) // { id, x, y }
  const simRef = useRef(null)

  // 컨테이너 크기 추적
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return undefined
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // 반지름: 면적 ∝ count, 전체 면적이 컨테이너의 ~50%
  const radii = useMemo(() => {
    const { w, h } = size
    if (!w || !h || !items.length) return {}
    const total = items.reduce((s, it) => s + Math.max(1, it.count), 0)
    const k = Math.sqrt((0.5 * w * h) / (Math.PI * total))
    const maxR = Math.min(w, h) / 3.2
    const out = {}
    items.forEach((it) => { out[it.id] = Math.max(18, Math.min(maxR, k * Math.sqrt(Math.max(1, it.count)))) })
    return out
  }, [items, size])

  // 시뮬레이션: 아이템/크기가 바뀔 때 다시 만든다. 기존 위치는 유지해서 튀지 않게
  useEffect(() => {
    const { w, h } = size
    if (!w || !h || !items.length) { setNodes([]); return undefined }
    const prev = new Map(nodes.map((n) => [n.id, n]))
    const sim = simRef.current
    const ns = items.map((it, i) => {
      const p = prev.get(it.id)
      const angle = (i / items.length) * Math.PI * 2
      return {
        ...it, r: radii[it.id],
        x: p?.x ?? w / 2 + Math.cos(angle) * w * 0.25, y: p?.y ?? h / 2 + Math.sin(angle) * h * 0.25,
        vx: p?.vx ?? 0, vy: p?.vy ?? 0, phase: p?.phase ?? Math.random() * Math.PI * 2, speed: p?.speed ?? 0.5 + Math.random() * 0.5,
      }
    })
    if (sim) sim.stop()
    const t0 = performance.now()
    const float = () => { // 느린 사인파로 떠다니는 힘
      const t = (performance.now() - t0) / 1000
      ns.forEach((n) => {
        n.vx += Math.cos(t * n.speed + n.phase) * 0.06
        n.vy += Math.sin(t * n.speed * 0.8 + n.phase * 1.7) * 0.06
      })
    }
    const bound = () => { // 화면 밖으로 나가지 않게. 선택 + 오버로 가장 크게 커졌을 때(약 10%)와 테두리 두께만큼 여유를 둔다
      ns.forEach((n) => {
        const pad = n.r * (MAX_SCALE - 1) + EDGE_PAD
        n.x = Math.max(n.r + pad, Math.min(w - n.r - pad, n.x))
        n.y = Math.max(n.r + pad, Math.min(h - n.r - pad, n.y))
      })
    }
    const s = forceSimulation(ns)
      .force('x', forceX(w / 2).strength(0.02))
      .force('y', forceY(h / 2).strength(0.02))
      .force('collide', forceCollide((n) => n.r + 4).strength(0.9).iterations(2))
      .force('float', float)
      .alphaDecay(0)        // 멈추지 않고 계속 움직인다
      .velocityDecay(0.35)
      .alpha(0.4)
      .on('tick', () => { bound(); setNodes(ns.map((n) => ({ ...n }))) })
    simRef.current = s
    return () => s.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, radii, size])

  return (
    <Box ref={wrapRef} sx={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      <svg width={size.w} height={size.h} style={{ display: 'block' }}>
        {nodes.map((n) => {
          const fs = Math.max(12, Math.min(19, n.r / 4.8))
          const lh = fs * 1.2
          const maxLines = Math.max(1, Math.floor((n.r * 1.7) / lh) - 1)
          const lines = n.r >= 22 ? [...wrapText(n.label, fs, n.r * 1.6, maxLines), `(${n.count}개)`] : []
          const y0 = -((lines.length - 1) * lh) / 2
          const selected = n.id === selectedId
          const hovered = hover?.id === n.id
          return (
            <g
              key={n.id}
              transform={`translate(${n.x},${n.y})`}
              style={{ cursor: 'pointer', opacity: selectedId && !selected ? 0.3 : 1, transition: 'opacity 0.2s' }}
              onMouseEnter={() => setHover({ id: n.id })}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(n)}
            >
              <circle
                r={n.r * (hovered ? HOVER_SCALE : 1) * (selected ? SELECT_SCALE : 1)}
                fill={n.color}
                stroke={selected ? '#18181b' : 'rgba(0,0,0,0.25)'}
                strokeWidth={selected ? 2 : 1}
              />
              <text textAnchor="middle" dominantBaseline="central" fill={n.textColor} style={{ fontSize: fs, fontWeight: 700, pointerEvents: 'none', fontFamily: 'inherit' }}>
                {lines.map((l, i) => (
                  <tspan key={i} x={0} y={y0 + i * lh} style={i === lines.length - 1 ? { fontWeight: 500, fontSize: fs * 0.85, opacity: 0.85 } : undefined}>{l}</tspan>
                ))}
              </text>
            </g>
          )
        })}
      </svg>
      {hover && (() => {
        const n = nodes.find((x) => x.id === hover.id)
        if (!n) return null
        const left = Math.min(size.w - 380, Math.max(8, n.x + n.r + 8))
        const top = Math.max(8, n.y - 24)
        return (
          <Box sx={{ position: 'absolute', left, top, pointerEvents: 'none', background: '#fff', border: '1px solid #e4e4e7', borderRadius: 1.5, px: 1.25, py: 0.75, fontSize: FONT_SIZES.sm, boxShadow: '0 4px 12px rgba(0,0,0,0.08)', maxWidth: 360, whiteSpace: 'nowrap', zIndex: 2 }}>
            <Box component="span" sx={{ display: 'inline-block', width: 10, height: 10, borderRadius: 0.5, backgroundColor: n.color, mr: 0.75, verticalAlign: 'middle' }} />
            <strong>{n.label}</strong>
            <Box component="span" sx={{ color: 'text.secondary', ml: 0.75 }}>{n.count}개 문서</Box>
            {n.tooltip && <Box sx={{ color: 'text.secondary', mt: 0.5, fontSize: FONT_SIZES.xs, whiteSpace: 'normal' }}>{n.tooltip}</Box>}
          </Box>
        )
      })()}
    </Box>
  )
}
