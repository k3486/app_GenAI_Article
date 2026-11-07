import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatPercent } from '@/lib/format'
import type { Insights } from '@/lib/types'

import { AXIS_STROKE, AXIS_TICK, GRID_STROKE } from './chart-theme'
import { ChartCard, ChartTooltip, SimpleTable } from './chart-kit'

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="bg-background rounded-lg border p-4">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="mt-1 text-3xl font-semibold">{value}</p>
      <p className="text-muted-foreground mt-1 text-xs">{note}</p>
    </div>
  )
}

/** 好みの学習の効き具合：選定記事の👍率・落選の「実はよかった」率・点数と👍率の関係。 */
export function EffectivenessPanel({
  effectiveness,
}: {
  effectiveness: Insights['effectiveness']
}) {
  const data = effectiveness.score_bins.map((b) => ({
    label: b.label,
    topics: b.topics,
    rate: b.like_rate === null ? null : Math.round(b.like_rate * 100),
  }))

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Tile
          label="選定記事の👍率"
          value={formatPercent(effectiveness.selected_like_rate)}
          note="評価した選定記事のうち👍の割合。高いほど、選定が好みに合っている"
        />
        <Tile
          label="落選記事の「実はよかった」率"
          value={formatPercent(effectiveness.rejected_missed_rate)}
          note="高いほど、基準が厳しすぎる（読みたい記事を落としている）"
        />
      </div>
      <ChartCard
        title="点数と👍率の関係"
        description="点数の帯ごとの👍率。点数が高いほど👍率が高ければ、採点は好みと合っています"
        chart={
          <div role="img" aria-label="点数の帯ごとの👍率の縦棒グラフ" className="h-52 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ left: -16, right: 8, top: 16 }}>
                <CartesianGrid vertical={false} stroke={GRID_STROKE} />
                <XAxis
                  dataKey="label"
                  tick={AXIS_TICK}
                  axisLine={{ stroke: AXIS_STROKE }}
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  unit="%"
                  tick={AXIS_TICK}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: 'var(--muted)', opacity: 0.5 }}
                  content={({ active, payload }) => {
                    const item = payload?.[0]?.payload as (typeof data)[number] | undefined
                    if (!item) return null
                    return (
                      <ChartTooltip
                        active={active}
                        title={item.label}
                        rows={[
                          {
                            color: 'var(--viz-1)',
                            label: '👍率',
                            value: item.rate === null ? '評価なし' : `${item.rate}%`,
                          },
                          {
                            color: 'var(--viz-other)',
                            label: '記事数',
                            value: `${item.topics} 件`,
                          },
                        ]}
                      />
                    )
                  }}
                />
                <Bar dataKey="rate" fill="var(--viz-1)" radius={[4, 4, 0, 0]} maxBarSize={44}>
                  <LabelList
                    dataKey="rate"
                    position="top"
                    formatter={(v: unknown) => (typeof v === 'number' ? `${v}%` : '')}
                    fill="var(--muted-foreground)"
                    fontSize={12}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        }
        table={
          <SimpleTable
            head={['点数の帯', '記事数', '👍率']}
            rows={data.map((d) => [d.label, d.topics, d.rate === null ? '評価なし' : `${d.rate}%`])}
          />
        }
      />
    </div>
  )
}
