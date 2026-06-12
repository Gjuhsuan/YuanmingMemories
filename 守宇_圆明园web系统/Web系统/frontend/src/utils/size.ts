/**
 * 前端节点尺寸计算 —— 与后端 degree.py 算法一致。
 * 用于前端临时合并邻居节点后的局部重算。
 */

/**
 * 对一组度数值做 95% 截顶 + sqrt 压缩 + 线性映射，返回节点像素尺寸。
 */
export function computeNodeSizes(
  degrees: number[],
  pxMin = 26,
  pxMax = 58,
): number[] {
  if (degrees.length === 0) return []
  if (degrees.length === 1) return [(pxMin + pxMax) / 2]

  const sorted = [...degrees].sort((a, b) => a - b)
  const idx95 = Math.min(Math.floor(sorted.length * 0.95), sorted.length - 1)
  const dCap = sorted[idx95]

  const sVals = degrees.map((d) => Math.sqrt(Math.max(Math.min(d, dCap), 0)))
  const sMin = Math.min(...sVals)
  const sMax = Math.max(...sVals)

  if (sMax === sMin) return degrees.map(() => (pxMin + pxMax) / 2)

  return sVals.map((s) => pxMin + (pxMax - pxMin) * (s - sMin) / (sMax - sMin))
}

/**
 * 根据节点像素尺寸计算标签字号。
 */
export function computeFontSize(nodeSize: number): number {
  return Math.max(10, Math.min(14, Math.round(nodeSize * 0.28)))
}

/**
 * 截断长标签（最多 12 汉字），超出加省略号。
 */
export function truncateLabel(name: string, max = 12): string {
  if (name.length <= max) return name
  return name.slice(0, max) + '…'
}
