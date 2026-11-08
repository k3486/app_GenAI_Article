import { ExternalLink } from 'lucide-react'

import { DigestView } from '@/components/DigestView'
import { ScoreBadge } from '@/components/ScoreBadge'
import { ScoreBreakdownView } from '@/components/ScoreBreakdownView'
import { StateActions } from '@/components/StateActions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDateTime } from '@/lib/format'
import {
  ARTICLE_TYPE_LABEL,
  CATEGORY_LABEL,
  DISLIKE_REASON_LABEL,
  SELECTION_LABEL,
} from '@/lib/labels'
import { usePatchState, useTopic } from '@/lib/queries'
import type { DislikeReason, TopicDetail } from '@/lib/types'
import { useTopicParam } from '@/lib/useTopicParam'

function RejectedActions({ topic }: { topic: TopicDetail }) {
  const { mutate } = usePatchState()
  return (
    <div className="bg-card flex flex-wrap items-center gap-3 rounded-lg border p-4">
      <p className="text-muted-foreground flex-1 text-sm">{topic.rejection_reason}</p>
      <Button
        type="button"
        variant={topic.state.missed ? 'default' : 'outline'}
        aria-pressed={topic.state.missed}
        onClick={() => mutate({ id: topic.id, patch: { missed: !topic.state.missed } })}
      >
        {topic.state.missed ? '「実はよかった」を付けました' : '実はよかった'}
      </Button>
    </div>
  )
}

function DislikeReasonPicker({ topic }: { topic: TopicDetail }) {
  const { mutate } = usePatchState()
  if (topic.state.rating !== 'dislike') return null
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">👎の理由（任意）</span>
      <Select
        value={topic.state.dislike_reason ?? 'none'}
        onValueChange={(v) =>
          mutate({
            id: topic.id,
            patch: { dislike_reason: v === 'none' ? null : (v as DislikeReason) },
          })
        }
      >
        <SelectTrigger aria-label="👎の理由" className="w-44">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">選ばない</SelectItem>
          {Object.entries(DISLIKE_REASON_LABEL).map(([value, label]) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function Body({ topic }: { topic: TopicDetail }) {
  const rejected = topic.selection === 'rejected'
  return (
    <div className="space-y-5">
      <DialogHeader className="space-y-3 text-left">
        <div className="flex flex-wrap items-center gap-2">
          <ScoreBadge score={topic.score} />
          <Badge variant="secondary">{ARTICLE_TYPE_LABEL[topic.article_type]}</Badge>
          <Badge variant="outline">{CATEGORY_LABEL[topic.category]}</Badge>
          {topic.selection !== 'selected' && (
            <Badge variant={rejected ? 'outline' : 'default'}>
              {SELECTION_LABEL[topic.selection]}
            </Badge>
          )}
          {topic.source_kind === 'official' && <Badge variant="secondary">公式</Badge>}
        </div>
        <DialogTitle className="text-xl leading-snug">{topic.title_ja}</DialogTitle>
        <DialogDescription>
          {topic.source_name}・公開 {formatDateTime(topic.published_at)}
          {topic.published_estimated && '（日付は推定）'}
          {topic.tags.length > 0 && `・${topic.tags.map((t) => `#${t}`).join(' ')}`}
        </DialogDescription>
        <div className="flex flex-wrap items-center gap-3">
          {!rejected && <StateActions topic={topic} />}
          <Button asChild variant="outline" size="sm" className="ml-auto">
            <a href={topic.url} target="_blank" rel="noopener noreferrer">
              元の記事を開く
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </a>
          </Button>
        </div>
        {!rejected && <DislikeReasonPicker topic={topic} />}
      </DialogHeader>

      {rejected && <RejectedActions topic={topic} />}

      {rejected && (
        <section aria-label="5行要約">
          <h3 className="mb-2 text-base font-semibold">5行要約</h3>
          <ol className="list-decimal space-y-1 pl-5 text-sm leading-relaxed">
            {topic.summary_5lines.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ol>
        </section>
      )}

      {topic.digest && <DigestView digest={topic.digest} articles={topic.articles} />}

      <ScoreBreakdownView breakdown={topic.breakdown} />
    </div>
  )
}

/** どのシートからでも `?topic=ID` で開く、記事の詳細（整理記事・点数の内訳）。 */
export function TopicDetailDialog() {
  const { topicId, close } = useTopicParam()
  const { data, isPending, isError } = useTopic(topicId)

  return (
    <Dialog open={topicId !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="max-h-[90svh] gap-0 overflow-y-auto p-5 sm:max-w-3xl sm:p-6">
        {isPending && topicId !== null && (
          <div className="space-y-4" aria-busy="true">
            <DialogTitle className="sr-only">読み込み中</DialogTitle>
            <DialogDescription className="sr-only">記事の詳細を読み込んでいます</DialogDescription>
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-40 w-full" />
          </div>
        )}
        {isError && (
          <div>
            <DialogTitle>記事を読み込めませんでした</DialogTitle>
            <DialogDescription>時間をおいてもう一度お試しください。</DialogDescription>
          </div>
        )}
        {data && <Body topic={data} />}
      </DialogContent>
    </Dialog>
  )
}
