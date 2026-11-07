import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { CATEGORY_LABEL } from '@/lib/labels'
import type { Insights } from '@/lib/types'

import { AXIS_STROKE, AXIS_TICK, CATEGORY_COLOR, GRID_STROKE } from './chart-theme'
import { ChartCard, ChartTooltip, SimpleTable } from './chart-kit'

/** トピックの内訳：大きさを比べるので横棒。色はカテゴリごとに固定。 */
export function CategoryBarChart({ categories }: { categories: Insights['categories'] }) {
  const total = categories.reduce((sum, c) => sum + c.count, 0)
  const data = categories.map((c) => ({
    category: c.category,
    name: CATEGORY_LABEL[c.category],
    count: c.count,
  }))

  return (
    <ChartCard
      title="トピックの内訳"
      description={`集めた記事 ${total} 件の分類（落選した記事も含む）`}
      chart={
        <div role="img" aria-label="トピックごとの記事数の横棒グラフ" className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 8, right: 32 }}
              barCategoryGap={10}
            >
              <CartesianGrid horizontal={false} stroke={GRID_STROKE} />
              <XAxis
                type="number"
                allowDecimals={false}
                tick={AXIS_TICK}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={150}
                tick={{ ...AXIS_TICK, fill: 'var(--muted-foreground)' }}
                axisLine={{ stroke: AXIS_STROKE }}
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
                      title={item.name}
                      rows={[
                        {
                          color: CATEGORY_COLOR[item.category],
                          label: '記事数',
                          value: `${item.count} 件（${Math.round((item.count / total) * 100)}%）`,
                        },
                      ]}
                    />
                  )
                }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22}>
                {data.map((d) => (
                  <Cell key={d.category} fill={CATEGORY_COLOR[d.category]} />
                ))}
                <LabelList
                  dataKey="count"
                  position="right"
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
          head={['トピック', '記事数', '割合']}
          rows={data.map((d) => [d.name, d.count, `${Math.round((d.count / total) * 100)}%`])}
        />
      }
    />
  )
}
