import React, { useEffect, useRef, useState } from 'react'
import { Box } from '@mui/material'
import { forceSimulation, forceX, forceY, forceCollide } from 'd3-force'

/**
 * 로딩용 떠다니는 점들. d3-force 로 작은 원들이 서로 겹치지 않으며 느리게 떠다닌다.
 * 완성된 버블 차트의 "빈 버전"처럼 보이도록 파란 계열 색을 쓴다.
 */
const DOT_COLORS = ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#1d4ed8', '#4f46e5', '#6366f1']
const DOT_COUNT = 22

export default function FloatingDots() {
  const wrapRef = useRef(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [nodes, setNodes] = useState([])
  const simRef = useRef(null)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return undefined
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const { w, h } = size
    if (!w || !h) { setNodes([]); return undefined }
    const ns = Array.from({ length: DOT_COUNT }, (_, i) => ({
      id: i,
      r: 6 + Math.random() * 8,
      color: DOT_COLORS[i % DOT_COLORS.length],
      x: w / 2 + (Math.random() - 0.5) * w * 0.6,
      y: h / 2 + (Math.random() - 0.5) * h * 0.6,
      vx: 0, vy: 0,
      phase: Math.random() * Math.PI * 2,
      speed: 0.4 + Math.random() * 0.5,
    }))
    if (simRef.current) simRef.current.stop()
    const t0 = performance.now()
    const float = () => {
      const t = (performance.now() - t0) / 1000
      ns.forEach((n) => {
        n.vx += Math.cos(t * n.speed + n.phase) * 0.05
        n.vy += Math.sin(t * n.speed * 0.8 + n.phase * 1.7) * 0.05
      })
    }
    const bound = () => {
      ns.forEach((n) => {
        const pad = 4
        n.x = Math.max(n.r + pad, Math.min(w - n.r - pad, n.x))
        n.y = Math.max(n.r + pad, Math.min(h - n.r - pad, n.y))
      })
    }
    const s = forceSimulation(ns)
      .force('x', forceX(w / 2).strength(0.015))
      .force('y', forceY(h / 2).strength(0.015))
      .force('collide', forceCollide((n) => n.r + 3).strength(0.9).iterations(2))
      .force('float', float)
      .alphaDecay(0)
      .velocityDecay(0.35)
      .alpha(0.4)
      .on('tick', () => { bound(); setNodes(ns.map((n) => ({ ...n }))) })
    simRef.current = s
    return () => s.stop()
  }, [size])

  return (
    <Box ref={wrapRef} sx={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      <svg width={size.w} height={size.h} style={{ display: 'block' }}>
        {nodes.map((n) => (
          <circle key={n.id} cx={n.x} cy={n.y} r={n.r} fill={n.color} opacity={0.55} />
        ))}
      </svg>
    </Box>
  )
}
