import { useState } from 'react'

import { FilterBar, type Filters } from '@/components/FilterBar'
import { CARD_GRID, EmptyState, ErrorNotice, PageHeader } from '@/components/PageHeader'
import { TopicCardView } from '@/components/TopicCardView'
import { Skeleton } from '@/components/ui/skeleton'
import { ARTICLE_TYPE_LABEL, CATEGORY_LABEL } from '@/lib/labels'
import { useTopics } from '@/lib/queries'
import type { TopicCard } from '@/lib/types'

function countBy(items: TopicCard[], key: (t: TopicCard) => string): [string, number][] {
  const counts = new Map<string, number>()
  for (const item of items) counts.set(key(item), (counts.get(key(item)) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1])
}

function Tendency({ title, rows }: { title: string; rows: [string, number][] }) {
  const max = Math.max(...rows.map(([, n]) => n), 1)
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <ul className="space-y-1.5">
        {rows.slice(0, 5).map(([label, n]) => (
          <li
            key={label}
            className="grid grid-cols-[minmax(0,1fr)_6rem_1.5rem] items-center gap-2 text-xs"
          >
            <span className="truncate">{label}</span>
            <span className="bg-border h-2 rounded-full" aria-hidden="true">
              <span
                className="bg-primary block h-full rounded-full"
                style={{ width: `${(n / max) * 100}%` }}
              />
            </span>
            <span className="text-muted-foreground text-right tabular-nums">{n}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function FavoritesPage() {
  const [filters, setFilters] = useState<Filters>({ q: '' })
  const { data, isPending, isError } = useTopics({ view: 'favorites', ...filters, pageSize: 100 })
  const items = data?.items ?? []

  return (
    <>
      <PageHeader
        title="お気に入り記事"
        description="★ を付けた記事です。あとで見返すための保存で、好みの学習（👍👎）とは別です。"
      />

      {items.length > 0 && (
        <section
          aria-label="お気に入りの傾向"
          className="bg-card mb-6 grid gap-6 rounded-xl border p-4 sm:grid-cols-3"
        >
          <Tendency title="トピック" rows={countBy(items, (t) => CATEGORY_LABEL[t.category])} />
          <Tendency title="情報源" rows={countBy(items, (t) => t.source_name)} />
          <Tendency
            title="記事の種類"
            rows={countBy(items, (t) => ARTICLE_TYPE_LABEL[t.article_type])}
          />
        </section>
      )}

      <div className="mb-6">
        <FilterBar filters={filters} onChange={setFilters} />
      </div>

      {isError && <ErrorNotice />}
      {isPending && (
        <div className={CARD_GRID} aria-busy="true">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-80 rounded-xl" />
          ))}
        </div>
      )}
      {data && items.length === 0 && (
        <EmptyState
          title="お気に入りの記事はまだありません"
          description="記事カードの ★ を押すと、ここに保存されます。"
        />
      )}
      <div className={CARD_GRID}>
        {items.map((t) => (
          <TopicCardView key={t.id} topic={t} />
        ))}
      </div>
    </>
  )
}
