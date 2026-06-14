/**
 * 配色常量 —— 前端唯一来源。
 * 严格按 CLAUDE.md 第 7 章。
 */

// 基础色（CSS 变量）
export const base = {
  bgCanvas: '#FAF8F3',
  bgPanel: '#FFFFFF',
  bgSubtle: '#F2EFE9',
  border: '#E3DED4',
  textPrimary: '#2B2A28',
  textSecondary: '#6B665E',
  textMuted: '#9A938A',
  accent: '#B5503C',
  edge: '#CFC8BC',
} as const

// 节点色（CLAIDE.md 7.3 节唯一权威来源）
export const nodeColors: Record<string, string> = {
  Event: '#B5503C',
  Person: '#5E7A99',
  Place: '#6E8E6A',
  Organization: '#8E7BA0',
  Object: '#B08A4F',
  Document: '#7C8691',
  AbstractNorm: '#A8836E',
  TemporalInterval: '#6FA0A0',
}

// 状态色
export const state = {
  dimmedOpacity: 0.12,
  highlightOpacity: 1.0,
  nodeMinSize: 26,
  nodeMaxSize: 58,
  edgeWidth: 1,
  selectedStroke: '#B5503C',
  selectedStrokeWidth: 2,
}
