import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { formatMonthDay } from '@/lib/format'
import { CATEGORY_LABEL, CATEGORY_ORDER } from '@/lib/labels'
import type { Category, Insights } from '@/lib/types'

import { AXIS_STROKE, AXIS_TICK, CATEGORY_COLOR, GAP_STROKE, GRID_STROKE } from './chart-theme'
import { CategoryLegend, ChartCard, ChartTooltip, SimpleTable } from './chart-kit'

type Row = { date: string; label: string } & Partial<Record<Category, number>>

function pivot(trend: Insights['trend']): Row[] {
  const byDate = new Map<string, Row>()
  for (const point of trend) {
    const row = byDate.get(point.date) ?? {
      date: point.date,
      label: formatMonthDay(`${point.date}T00:00:00+09:00`),
    }
    row[point.category] = (row[point.category] ?? 0) + point.count
    byDate.set(point.date, row)
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))
}

/** 話題の推移：日ごとの件数の内訳なので、積み上げ縦棒。 */
export function CategoryTrendChart({ trend }: { trend: Insights['trend'] }) {
  const data = pivot(trend)
  const used = CATEGORY_ORDER.filter((c) => data.some((row) => (row[c] ?? 0) > 0))

  return (
    <ChartCard
      title="話題の推移"
      description="日ごとに集めた記事のトピック別の件数"
      legend={<CategoryLegend categories={used} />}
      chart={
        <div
          role="img"
          aria-label="日ごとのトピック別記事数の積み上げ縦棒グラフ"
          className="h-72 w-full"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ left: -16, right: 8 }}>
              <CartesianGrid vertical={false} stroke={GRID_STROKE} />
              <XAxis
                dataKey="label"
                tick={AXIS_TICK}
                axisLine={{ stroke: AXIS_STROKE }}
                tickLine={false}
              />
              <YAxis allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: 'var(--muted)', opacity: 0.5 }}
                content={({ active, label, payload }) => (
                  <ChartTooltip
                    active={active}
                    title={String(label ?? '')}
                    rows={(payload ?? [])
                      .filter((p) => Number(p.value) > 0)
                      .map((p) => ({
                        color: CATEGORY_COLOR[p.dataKey as Category],
                        label: CATEGORY_LABEL[p.dataKey as Category],
                        value: `${p.value} 件`,
                      }))}
                  />
                )}
              />
              {used.map((category, i) => (
                <Bar
                  key={category}
                  dataKey={category}
                  stackId="topics"
                  fill={CATEGORY_COLOR[category]}
                  stroke={GAP_STROKE}
                  strokeWidth={2}
                  radius={i === used.length - 1 ? [4, 4, 0, 0] : 0}
                  maxBarSize={44}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      }
      table={
        <SimpleTable
          head={['日付', ...used.map((c) => CATEGORY_LABEL[c])]}
          rows={data.map((row) => [row.label, ...used.map((c) => row[c] ?? 0)])}
        />
      }
    />
  )
}
