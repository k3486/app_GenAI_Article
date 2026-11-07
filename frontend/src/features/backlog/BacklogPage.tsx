import { Check, X } from 'lucide-react'
import { useState } from 'react'

import { BacklogTrendChart } from '@/components/charts/BacklogTrendChart'
import { EmptyState, ErrorNotice, PageHeader } from '@/components/PageHeader'
import { ScoreBadge } from '@/components/ScoreBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ARTICLE_TYPE_LABEL } from '@/lib/labels'
import { useInsights, usePatchState, useTopics } from '@/lib/queries'
import type { TopicCard } from '@/lib/types'
import { useTopicParam } from '@/lib/useTopicParam'
import { cn } from '@/lib/utils'

/** 未読のまま 30 日たった記事は、自動で「見送り」にする（「後で読む」は除く）。 */
const AUTO_DISMISS_DAYS = 30
const WARN_DAYS = 21

type Sort = 'oldest' | 'score'

function ageDays(topic: TopicCard): number {
  return Math.max(0, Math.floor((Date.now() - Date.parse(topic.selected_at)) / 86_400_000))
}

function Row({ topic }: { topic: TopicCard }) {
  const { open } = useTopicParam()
  const { mutate } = usePatchState()
  const age = ageDays(topic)
  const pinned = topic.state.backlog
  const warn = !pinned && age >= WARN_DAYS

  return (
    <li className="bg-card flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border p-3 sm:px-4">
      <ScoreBadge score={topic.score} />
      <div className="min-w-0 flex-1 basis-64">
        <button
          type="button"
          onClick={() => open(topic.id)}
          className="line-clamp-2 text-left font-medium hover:underline focus-visible:underline focus-visible:outline-none"
        >
          {topic.title_ja}
        </button>
        <p className="text-muted-foreground mt-0.5 text-xs">
          {topic.source_name}・{ARTICLE_TYPE_LABEL[topic.article_type]}
        </p>
      </div>
      <div className="flex items-center gap-2 text-xs">
        {pinned && <Badge variant="secondary">後で読む</Badge>}
        <span
          className={cn(
            'tabular-nums',
            warn ? 'text-foreground font-medium' : 'text-muted-foreground',
          )}
        >
          {age === 0 ? '今日選定' : `${age}日前に選定`}
          {warn && `・あと${AUTO_DISMISS_DAYS - age}日で見送り`}
        </span>
      </div>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => mutate({ id: topic.id, patch: { read_state: 'read', backlog: false } })}
        >
          <Check className="size-4" aria-hidden="true" />
          読んだ
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() =>
            mutate({
              id: topic.id,
              patch: {
                read_state: 'dismissed',
                backlog: false,
                rating: 'dislike',
                dislike_reason: 'not_interested',
              },
            })
          }
        >
          <X className="size-4" aria-hidden="true" />
          興味なし
        </Button>
      </div>
    </li>
  )
}

export function BacklogPage() {
  const [sort, setSort] = useState<Sort>('oldest')
  const topics = useTopics({ view: 'backlog', pageSize: 200 })
  const insights = useInsights()
  const items = [...(topics.data?.items ?? [])].sort((a, b) =>
    sort === 'oldest'
      ? Date.parse(a.selected_at) - Date.parse(b.selected_at) || b.score - a.score
      : b.score - a.score,
  )

  return (
    <>
      <PageHeader
        title="バックログ"
        description={`読み残した記事です。未読の選定記事は自動で入り、未読のまま${AUTO_DISMISS_DAYS}日たつと「見送り」になります（「後で読む」にした記事は除く）。`}
      />

      {insights.data && (
        <div className="mb-6">
          <BacklogTrendChart backlog={insights.data.backlog} />
        </div>
      )}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">
          未読 <span className="tabular-nums">{items.length}</span> 件
        </h2>
        <div className="inline-flex rounded-lg border p-0.5" role="group" aria-label="並び順">
          {(
            [
              ['oldest', '古い順'],
              ['score', '点数順'],
            ] as const
          ).map(([value, label]) => (
            <Button
              key={value}
              type="button"
              size="sm"
              variant={sort === value ? 'secondary' : 'ghost'}
              aria-pressed={sort === value}
              className="h-7 px-2.5 text-xs"
              onClick={() => setSort(value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {topics.isError && <ErrorNotice />}
      {topics.isPending && (
        <div className="space-y-2" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      )}
      {topics.data && items.length === 0 && (
        <EmptyState
          title="読み残した記事はありません"
          description="新しい記事が選ばれると、ここに入ります。"
        />
      )}
      <ul className="space-y-2">
        {items.map((t) => (
          <Row key={t.id} topic={t} />
        ))}
      </ul>
    </>
  )
}
