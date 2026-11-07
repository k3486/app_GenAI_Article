/** グラフの共通部品：色・軸の見た目・ツールチップ・凡例・「グラフ／表」の切り替え枠。 */
import { useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { CATEGORY_LABEL, CATEGORY_ORDER } from '@/lib/labels'
import type { Category } from '@/lib/types'
import { cn } from '@/lib/utils'

import { CATEGORY_COLOR } from './chart-theme'

export function CategoryLegend({ categories = CATEGORY_ORDER }: { categories?: Category[] }) {
  return (
    <ul className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="凡例">
      {categories.map((c) => (
        <li key={c} className="inline-flex items-center gap-1.5">
          <span
            className="size-2.5 rounded-sm"
            style={{ backgroundColor: CATEGORY_COLOR[c] }}
            aria-hidden="true"
          />
          {CATEGORY_LABEL[c]}
        </li>
      ))}
    </ul>
  )
}

type TooltipRow = { color: string; label: string; value: string | number }

/** ホバーで出す吹き出し（文字は本文の色。色の四角で系列を示す） */
export function ChartTooltip({
  active,
  title,
  rows,
}: {
  active?: boolean
  title: string
  rows: TooltipRow[]
}) {
  if (!active || rows.length === 0) return null
  return (
    <div className="bg-popover text-popover-foreground rounded-lg border px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium">{title}</p>
      <ul className="space-y-0.5">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center gap-2">
            <span
              className="size-2.5 rounded-sm"
              style={{ backgroundColor: r.color }}
              aria-hidden="true"
            />
            <span className="flex-1">{r.label}</span>
            <span className="tabular-nums">{r.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** グラフと、同じ数字の表を切り替えられる枠。表は色に頼れない人や読み上げのための代替。 */
export function ChartCard({
  title,
  description,
  legend,
  chart,
  table,
  className,
}: {
  title: string
  description?: string
  legend?: ReactNode
  chart: ReactNode
  table: ReactNode
  className?: string
}) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  return (
    <section className={cn('bg-card rounded-xl border p-4 sm:p-5', className)}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {description && <p className="text-muted-foreground mt-0.5 text-xs">{description}</p>}
        </div>
        <div
          className="inline-flex rounded-lg border p-0.5"
          role="group"
          aria-label={`${title}の表示`}
        >
          {(['chart', 'table'] as const).map((v) => (
            <Button
              key={v}
              type="button"
              size="sm"
              variant={view === v ? 'secondary' : 'ghost'}
              aria-pressed={view === v}
              className="h-7 px-2.5 text-xs"
              onClick={() => setView(v)}
            >
              {v === 'chart' ? 'グラフ' : '表'}
            </Button>
          ))}
        </div>
      </div>
      {view === 'chart' ? (
        <>
          {legend && <div className="mb-3">{legend}</div>}
          {chart}
        </>
      ) : (
        <div className="overflow-x-auto">{table}</div>
      )}
    </section>
  )
}

export function SimpleTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="w-full text-sm">
      <thead className="text-muted-foreground border-b text-left text-xs">
        <tr>
          {head.map((h) => (
            <th key={h} scope="col" className="px-2 py-2 font-medium whitespace-nowrap">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-b last:border-0">
            {row.map((cell, j) => (
              <td key={j} className={cn('px-2 py-2', j > 0 && 'tabular-nums')}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
