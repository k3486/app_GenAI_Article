import { Link2, Siren } from 'lucide-react'

import { ScoreBadge } from '@/components/ScoreBadge'
import { StateActions } from '@/components/StateActions'
import { ThumbArt } from '@/components/ThumbArt'
import { Badge } from '@/components/ui/badge'
import { formatMonthDay } from '@/lib/format'
import { ARTICLE_TYPE_LABEL, CATEGORY_LABEL, READ_STATE_LABEL } from '@/lib/labels'
import type { TopicCard } from '@/lib/types'
import { useTopicParam } from '@/lib/useTopicParam'
import { cn } from '@/lib/utils'

/** 一覧に並べる記事カード（画像・点数・題名・1行要約・操作）。 */
export function TopicCardView({ topic }: { topic: TopicCard }) {
  const { open } = useTopicParam()
  const read = topic.state.read_state !== 'unread'

  return (
    <article
      className={cn(
        'group bg-card focus-within:ring-ring flex flex-col overflow-hidden rounded-xl border shadow-xs transition-shadow focus-within:ring-2 hover:shadow-md',
        read && 'opacity-75',
      )}
    >
      <button
        type="button"
        onClick={() => open(topic.id)}
        className="flex flex-1 flex-col text-left outline-none"
        aria-label={`${topic.title_ja} の詳細を開く`}
      >
        <div className="relative aspect-video w-full overflow-hidden">
          <ThumbArt imageUrl={topic.image_url} category={topic.category} />
          <ScoreBadge score={topic.score} className="absolute top-3 left-3 shadow-sm" />
          <div className="absolute top-3 right-3 flex gap-1.5">
            {topic.selection === 'major' && (
              <Badge className="bg-status-critical gap-1 text-white">
                <Siren className="size-3" aria-hidden="true" />
                重大ニュース
              </Badge>
            )}
            {topic.source_kind === 'official' && <Badge variant="secondary">公式</Badge>}
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-2 p-4">
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className="text-foreground/80 font-medium">
              {ARTICLE_TYPE_LABEL[topic.article_type]}
            </span>
            <span aria-hidden="true">·</span>
            <span>{CATEGORY_LABEL[topic.category]}</span>
            {read && (
              <Badge variant="outline" className="ml-auto">
                {READ_STATE_LABEL[topic.state.read_state]}
              </Badge>
            )}
          </div>
          <h3 className="line-clamp-2 text-base leading-snug font-semibold">{topic.title_ja}</h3>
          <p className="text-muted-foreground line-clamp-2 text-sm leading-relaxed">
            {topic.summary_1line}
          </p>
          <div className="text-muted-foreground mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 text-xs">
            <span className="truncate">{topic.source_name}</span>
            <span aria-hidden="true">·</span>
            <span>
              {formatMonthDay(topic.published_at)}
              {topic.published_estimated && '（推定）'}
            </span>
            {topic.related_count > 0 && (
              <span className="ml-auto inline-flex items-center gap-1">
                <Link2 className="size-3" aria-hidden="true" />
                関連 {topic.related_count}
              </span>
            )}
          </div>
        </div>
      </button>
      <div className="flex items-center justify-between border-t px-2 py-1.5">
        <StateActions topic={topic} />
      </div>
    </article>
  )
}
