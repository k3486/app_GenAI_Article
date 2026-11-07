import { Siren } from 'lucide-react'
import { useState } from 'react'

import { FilterBar, type Filters } from '@/components/FilterBar'
import { CARD_GRID, EmptyState, ErrorNotice, PageHeader } from '@/components/PageHeader'
import { TopicCardView } from '@/components/TopicCardView'
import { Skeleton } from '@/components/ui/skeleton'
import { runDayLabel } from '@/lib/format'
import { useTopics } from '@/lib/queries'
import type { TopicCard } from '@/lib/types'

/** 更新の回ごとに区切る（今日→昨日→…）。中は点数の高い順（API が並べて返す）。 */
function groupByRun(items: TopicCard[]): { runId: number; label: string; items: TopicCard[] }[] {
  const groups = new Map<number, TopicCard[]>()
  for (const item of items) {
    const list = groups.get(item.run_id) ?? []
    list.push(item)
    groups.set(item.run_id, list)
  }
  return [...groups.entries()].map(([runId, list]) => ({
    runId,
    label: runDayLabel(list[0]!.selected_at),
    items: list,
  }))
}

function LoadingGrid() {
  return (
    <div className={CARD_GRID} aria-busy="true">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-80 rounded-xl" />
      ))}
    </div>
  )
}

export function LatestPage() {
  const [filters, setFilters] = useState<Filters>({ q: '' })
  const { data, isPending, isError } = useTopics({ view: 'latest', ...filters, pageSize: 100 })

  const items = data?.items ?? []
  const majors = items.filter((t) => t.selection === 'major')
  const groups = groupByRun(items.filter((t) => t.selection !== 'major'))

  return (
    <>
      <PageHeader
        title="最新トピック"
        description="直近7日に選ばれた記事です。更新の回ごとに、点数の高い順に並びます。"
      />
      <div className="mb-6">
        <FilterBar filters={filters} onChange={setFilters} />
      </div>

      {isError && <ErrorNotice />}
      {isPending && <LoadingGrid />}
      {data && items.length === 0 && (
        <EmptyState
          title="条件に合う記事がありません"
          description="絞り込みを変えるか、右上の「更新」で新しい記事を集めてください。"
        />
      )}

      {majors.length > 0 && (
        <section className="mb-10" aria-labelledby="major-heading">
          <h2
            id="major-heading"
            className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-lg font-semibold"
          >
            <Siren className="text-status-critical size-5" aria-hidden="true" />
            重大ニュース
            <span className="text-muted-foreground w-full text-sm font-normal sm:w-auto">
              関心は低くても、業界への影響が大きい話題です
            </span>
          </h2>
          <div className={CARD_GRID}>
            {majors.map((t) => (
              <TopicCardView key={t.id} topic={t} />
            ))}
          </div>
        </section>
      )}

      {groups.map((group) => (
        <section key={group.runId} className="mb-10" aria-labelledby={`run-${group.runId}`}>
          <h2
            id={`run-${group.runId}`}
            className="mb-3 flex items-baseline gap-2 text-lg font-semibold"
          >
            {group.label}
            <span className="text-muted-foreground text-sm font-normal">
              {group.items.length} 件
            </span>
          </h2>
          <div className={CARD_GRID}>
            {group.items.map((t) => (
              <TopicCardView key={t.id} topic={t} />
            ))}
          </div>
        </section>
      ))}
    </>
  )
}
