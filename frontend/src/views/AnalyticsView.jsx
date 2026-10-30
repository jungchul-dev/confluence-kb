import React, { useCallback, useEffect, useState } from 'react'
import { Box, Typography, TextField, Button, Card, Alert, Link, Chip } from '@mui/material'
import { ResponsiveCirclePacking } from '@nivo/circle-packing'
import * as api from '../api'

const CLUSTER_COLORS = ['#2563eb', '#16a34a', '#dc2626', '#9333ea', '#ea580c', '#0891b2', '#ca8a04', '#be185d',
  '#4f46e5', '#059669', '#db2777', '#7c3aed', '#0d9488', '#c2410c', '#4338ca', '#0284c7']

export default function AnalyticsView() {
  const [clusters, setClusters] = useState([])
  const [totalDocs, setTotalDocs] = useState(0)
  const [k, setK] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const data = await api.getClusters(k)
      setClusters(data.clusters); setTotalDocs(data.total_documents); setK(data.k)
      setSelected(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [k])

  const shortTitle = (title) => {
    const stripped = title.replace(/\s*—\s*.*$/, '').replace(/\s*>\s*/g, ' › ')
    return stripped.length > 20 ? stripped.slice(0, 20) + '…' : stripped
  }

  const bubbleData = {
    id: '전체',
    color: '#f4f4f5',
    children: clusters.map((c, i) => ({
      id: c.representative_docs[0] ? shortTitle(c.representative_docs[0].title) : `클러스터 ${c.cluster_id}`,
      value: c.doc_count,
      color: CLUSTER_COLORS[i % CLUSTER_COLORS.length],
      cluster: c,
    })),
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }}>
        <Typography color="text.secondary">클러스터 수</Typography>
        <TextField type="number" size="small" sx={{ width: 70 }} slotProps={{ htmlInput: { min: 0, max: 50 } }} value={k} onChange={(e) => setK(Number(e.target.value))} />
        <Button variant="contained" size="small" sx={{ flexShrink: 0, whiteSpace: 'nowrap' }} onClick={load} disabled={loading}>{loading ? '분석 중…' : '분석'}</Button>
        <Typography color="text.secondary">(0 = 자동)</Typography>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Typography color="text.secondary" sx={{ mb: 2 }}>전체 문서 {totalDocs}개 · 클러스터 {clusters.length}개</Typography>

      {clusters.length > 0 && (
        <Box sx={{ display: 'flex', gap: 2 }}>
          {/* 버블 차트 */}
          <Box sx={{ height: 500, flex: 1, minWidth: 0 }}>
            <ResponsiveCirclePacking
              data={bubbleData}
              margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
              padding={10}
              colors={({ data }) => data.color || '#e4e4e7'}
              colorBy="id"
              enableLabels
              label={({ data }) => data.id}
              labelTextColor={({ data }) => {
                const hex = data.color || '#e4e4e7'
                const r = parseInt(hex.slice(1, 3), 16)
                const g = parseInt(hex.slice(3, 5), 16)
                const b = parseInt(hex.slice(5, 7), 16)
                const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                return luminance > 0.55 ? '#18181b' : '#ffffff'
              }}
              labelSkipRadius={12}
              fontSize={14}
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
            <Card variant="outlined" sx={{ p: 2, width: 360, flexShrink: 0, alignSelf: 'flex-start' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <Chip size="small" label={`클러스터 ${selected.cluster_id}`} sx={{ backgroundColor: CLUSTER_COLORS[clusters.findIndex(c => c.cluster_id === selected.cluster_id) % CLUSTER_COLORS.length], color: '#fff', fontWeight: 600 }} />
                <Typography color="text.secondary">{selected.doc_count}개 문서</Typography>
              </Box>
              {selected.representative_docs.map((d) => (
                <Box key={d.document_id} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, py: 0.75, borderTop: 1, borderColor: 'divider', fontSize: '0.8125rem', '&:first-of-type': { borderTop: 0 } }}>
                  <Chip size="small" label={d.kind === 'attachment' ? '첨부' : '페이지'} color={d.kind === 'attachment' ? 'success' : 'primary'} variant="filled" />
                  <Link href={d.url} target="_blank" rel="noreferrer">{d.title}</Link>
                </Box>
              ))}
              {selected.all_titles.length > selected.representative_docs.length && (
                <Typography color="text.secondary" sx={{ fontSize: '0.75rem', mt: 1.5 }}>외 {selected.all_titles.length - selected.representative_docs.length}개 문서</Typography>
              )}
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
