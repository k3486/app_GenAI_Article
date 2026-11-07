/** グラフの色と軸の見た目（値は index.css のテーマ変数。ライト／ダークで自動で切り替わる）。 */
import type { Category } from '@/lib/types'

/** カテゴリの色は固定（絞り込みで系列が減っても、残りの色は変えない） */
export const CATEGORY_COLOR: Record<Category, string> = {
  dev_tools_agents: 'var(--viz-1)',
  models: 'var(--viz-2)',
  use_cases: 'var(--viz-3)',
  know_how: 'var(--viz-4)',
  regulation_safety: 'var(--viz-5)',
  industry_trends: 'var(--viz-6)',
  other: 'var(--viz-other)',
}

export const AXIS_TICK = { fill: 'var(--ink-muted)', fontSize: 12 }
export const GRID_STROKE = 'var(--hairline)'
export const AXIS_STROKE = 'var(--border)'
/** 積み上げ・隣り合う棒の間に入れる 2px の面色の隙間 */
export const GAP_STROKE = 'var(--card)'
