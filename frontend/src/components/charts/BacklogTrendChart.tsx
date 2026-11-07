import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { formatMonthDay } from '@/lib/format'
import type { Insights } from '@/lib/types'

import { AXIS_STROKE, AXIS_TICK, GRID_STROKE } from './chart-theme'
import { ChartCard, ChartTooltip, SimpleTable } from './chart-kit'

/** バックログ残数の推移：1本の時系列なので、線＋うすい面。 */
export function BacklogTrendChart({ backlog }: { backlog: Insights['backlog'] }) {
  const data = backlog.map((p) => ({
    label: formatMonthDay(`${p.date}T00:00:00+09:00`),
    count: p.count,
  }))
  const latest = data.at(-1)

  return (
    <ChartCard
      title="バックログ残数の推移"
      description={latest ? `直近14日。いまの残数は ${latest.count} 件` : '直近14日'}
      chart={
        <div role="img" aria-label="バックログ残数の折れ線グラフ" className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ left: -16, right: 16 }}>
              <CartesianGrid vertical={false} stroke={GRID_STROKE} />
              <XAxis
                dataKey="label"
                tick={AXIS_TICK}
                axisLine={{ stroke: AXIS_STROKE }}
                tickLine={false}
                interval="preserveStartEnd"
                minTickGap={24}
              />
              <YAxis allowDecimals={false} tick={AXIS_TICK} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ stroke: 'var(--border)' }}
                content={({ active, label, payload }) => (
                  <ChartTooltip
                    active={active}
                    title={String(label ?? '')}
                    rows={
                      payload?.[0]
                        ? [
                            {
                              color: 'var(--viz-1)',
                              label: '残数',
                              value: `${payload[0].value} 件`,
                            },
                          ]
                        : []
                    }
                  />
                )}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="var(--viz-1)"
                strokeWidth={2}
                fill="var(--viz-1)"
                fillOpacity={0.12}
                dot={false}
                activeDot={{ r: 4, stroke: 'var(--card)', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      }
      table={<SimpleTable head={['日付', '残数']} rows={data.map((d) => [d.label, d.count])} />}
    />
  )
}
