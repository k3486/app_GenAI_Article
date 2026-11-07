import {
  createColumnHelper,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type SortingState,
} from '@tanstack/react-table'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ExternalLink,
  Star,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import { useMemo, useState } from 'react'

import { FilterBar, type Filters } from '@/components/FilterBar'
import { ScoreBadge } from '@/components/ScoreBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { formatMonthDay } from '@/lib/format'
import { ARTICLE_TYPE_LABEL, CATEGORY_LABEL, READ_STATE_LABEL } from '@/lib/labels'
import { usePatchState, useTopics, type SortKey } from '@/lib/queries'
import type { TopicCard } from '@/lib/types'
import { useTopicParam } from '@/lib/useTopicParam'
import { cn } from '@/lib/utils'

// 表は、サーバー側で並べ替え・ページ分けをする（並べ替えの機能だけを使う）
const features = tableFeatures({ rowSortingFeature })
const columnHelper = createColumnHelper<typeof features, TopicCard>()

const SORTABLE: ReadonlySet<string> = new Set<SortKey>([
  'score',
  'published_at',
  'selected_at',
  'title_ja',
  'source_name',
])

function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

function TitleCell({ topic }: { topic: TopicCard }) {
  const { open } = useTopicParam()
  return (
    <button
      type="button"
      onClick={() => open(topic.id)}
      className="max-w-72 text-left font-medium hover:underline focus-visible:underline focus-visible:outline-none"
    >
      {topic.title_ja}
    </button>
  )
}

function UrlCell({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary inline-flex max-w-44 items-center gap-1 truncate hover:underline"
    >
      <span className="truncate">{hostOf(url)}</span>
      <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
    </a>
  )
}

function StarCell({ topic }: { topic: TopicCard }) {
  const { mutate } = usePatchState()
  const on = topic.state.starred
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="size-8"
      aria-label={on ? 'お気に入りから外す' : 'お気に入りに保存（★）'}
      aria-pressed={on}
      onClick={() => mutate({ id: topic.id, patch: { starred: !on } })}
    >
      <Star className={cn('size-4', on && 'text-primary fill-current')} />
    </Button>
  )
}

function RatingCell({ topic }: { topic: TopicCard }) {
  const { mutate } = usePatchState()
  const { rating } = topic.state
  return (
    <div className="flex">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-8"
        aria-label="好み：いい（👍）"
        aria-pressed={rating === 'like'}
        onClick={() =>
          mutate({ id: topic.id, patch: { rating: rating === 'like' ? null : 'like' } })
        }
      >
        <ThumbsUp className={cn('size-4', rating === 'like' && 'text-primary fill-current')} />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-8"
        aria-label="好み：よくない（👎）"
        aria-pressed={rating === 'dislike'}
        onClick={() =>
          mutate({ id: topic.id, patch: { rating: rating === 'dislike' ? null : 'dislike' } })
        }
      >
        <ThumbsDown className={cn('size-4', rating === 'dislike' && 'text-primary fill-current')} />
      </Button>
    </div>
  )
}

function MissedCell({ topic }: { topic: TopicCard }) {
  const { mutate } = usePatchState()
  const on = topic.state.missed
  return (
    <Button
      type="button"
      size="sm"
      variant={on ? 'default' : 'outline'}
      aria-pressed={on}
      onClick={() => mutate({ id: topic.id, patch: { missed: !on } })}
    >
      {on ? '実はよかった ✓' : '実はよかった'}
    </Button>
  )
}

const common = {
  title: columnHelper.accessor('title_ja', {
    id: 'title_ja',
    header: '日本語タイトル',
    cell: ({ row }) => <TitleCell topic={row.original} />,
  }),
  url: columnHelper.accessor('url', {
    id: 'url',
    header: 'URL',
    enableSorting: false,
    cell: ({ row }) => <UrlCell url={row.original.url} />,
  }),
  score: columnHelper.accessor('score', {
    id: 'score',
    header: '点数',
    cell: ({ row }) => <ScoreBadge score={row.original.score} />,
  }),
  type: columnHelper.accessor('article_type', {
    id: 'article_type',
    header: '種類',
    enableSorting: false,
    cell: ({ row }) => (
      <span className="whitespace-nowrap">{ARTICLE_TYPE_LABEL[row.original.article_type]}</span>
    ),
  }),
  category: columnHelper.accessor('category', {
    id: 'category',
    header: 'トピック',
    enableSorting: false,
    cell: ({ row }) => (
      <span className="whitespace-nowrap">{CATEGORY_LABEL[row.original.category]}</span>
    ),
  }),
  source: columnHelper.accessor('source_name', {
    id: 'source_name',
    header: '情報源',
    cell: ({ row }) => <span className="whitespace-nowrap">{row.original.source_name}</span>,
  }),
  published: columnHelper.accessor('published_at', {
    id: 'published_at',
    header: '発表日',
    cell: ({ row }) => (
      <span className="whitespace-nowrap tabular-nums">
        {formatMonthDay(row.original.published_at)}
        {row.original.published_estimated && '（推定）'}
      </span>
    ),
  }),
}

const selectedColumns = columnHelper.columns([
  common.title,
  columnHelper.accessor('summary_1line', {
    id: 'summary_1line',
    header: '1行要約',
    enableSorting: false,
    cell: ({ row }) => (
      <p className="text-muted-foreground line-clamp-2 w-72">{row.original.summary_1line}</p>
    ),
  }),
  common.url,
  columnHelper.display({
    id: 'star',
    header: '★',
    cell: ({ row }) => <StarCell topic={row.original} />,
  }),
  columnHelper.display({
    id: 'rating',
    header: '👍👎',
    cell: ({ row }) => <RatingCell topic={row.original} />,
  }),
  columnHelper.display({
    id: 'state',
    header: '状態',
    cell: ({ row }) => (
      <Badge variant={row.original.state.read_state === 'unread' ? 'default' : 'outline'}>
        {READ_STATE_LABEL[row.original.state.read_state]}
      </Badge>
    ),
  }),
  common.score,
  common.type,
  common.category,
  common.source,
  common.published,
  columnHelper.accessor('selected_at', {
    id: 'selected_at',
    header: '選定日',
    cell: ({ row }) => (
      <span className="whitespace-nowrap tabular-nums">
        {formatMonthDay(row.original.selected_at)}
      </span>
    ),
  }),
])

const rejectedColumns = columnHelper.columns([
  common.title,
  columnHelper.accessor('summary_5lines', {
    id: 'summary_5lines',
    header: '5行要約',
    enableSorting: false,
    cell: ({ row }) => (
      <p className="text-muted-foreground line-clamp-3 w-80">
        {row.original.summary_5lines.join(' ')}
      </p>
    ),
  }),
  common.url,
  common.score,
  columnHelper.display({
    id: 'breakdown',
    header: '内訳（関心・実用・新しさ・信頼・深さ）',
    cell: ({ row }) => (
      <span className="whitespace-nowrap tabular-nums">
        {row.original.breakdown.criteria.map((c) => c.score).join(' · ')}
      </span>
    ),
  }),
  columnHelper.accessor('rejection_reason', {
    id: 'rejection_reason',
    header: '落選の理由',
    enableSorting: false,
    cell: ({ row }) => (
      <p className="text-muted-foreground line-clamp-2 w-56">{row.original.rejection_reason}</p>
    ),
  }),
  common.type,
  common.category,
  common.source,
  common.published,
  columnHelper.accessor('selected_at', {
    id: 'selected_at',
    header: '登録日',
    cell: ({ row }) => (
      <span className="whitespace-nowrap tabular-nums">
        {formatMonthDay(row.original.selected_at)}
      </span>
    ),
  }),
  columnHelper.display({
    id: 'missed',
    header: '判定への意見',
    cell: ({ row }) => <MissedCell topic={row.original} />,
  }),
])

const PAGE_SIZES = [10, 25, 50]

/** 横にスクロールしても、題名の列は左に残す */
const STICKY_TITLE = 'sticky left-0 z-10 border-r shadow-[2px_0_4px_-2px_rgba(0,0,0,0.08)]'

/** 選定済み／落選記事の表。並べ替え・絞り込み・検索・ページ送りはサーバーで行う。 */
export function TopicTable({ variant }: { variant: 'selected' | 'rejected' }) {
  const [filters, setFilters] = useState<Filters>({ q: '' })
  const [sorting, setSorting] = useState<SortingState>([{ id: 'selected_at', desc: true }])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const sort = sorting[0]
  const sortKey = sort && SORTABLE.has(sort.id) ? (sort.id as SortKey) : undefined
  const { data, isPending, isError, isPlaceholderData } = useTopics({
    view: variant === 'selected' ? 'all' : 'rejected',
    ...filters,
    sort: sortKey,
    order: sort?.desc === false ? 'asc' : 'desc',
    page,
    pageSize,
  })

  const columns = useMemo(
    () => (variant === 'selected' ? selectedColumns : rejectedColumns),
    [variant],
  )
  const table = useTable({
    features,
    columns,
    data: data?.items ?? [],
    getRowId: (row) => String(row.id),
    manualSorting: true,
    enableMultiSort: false,
    state: { sorting },
    onSortingChange: (updater) => {
      setSorting(updater)
      setPage(1)
    },
  })

  const total = data?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <div className="space-y-4">
      <FilterBar
        filters={filters}
        onChange={(next) => {
          setFilters(next)
          setPage(1)
        }}
      />

      {isError ? (
        <p
          role="alert"
          className="border-destructive/40 text-destructive rounded-lg border p-4 text-sm"
        >
          一覧を読み込めませんでした。時間をおいてもう一度お試しください。
        </p>
      ) : (
        <div
          className={cn(
            'bg-card overflow-x-auto rounded-xl border transition-opacity',
            isPlaceholderData && 'opacity-60',
          )}
        >
          <table className="w-full min-w-max text-sm">
            <thead className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => {
                    const canSort = header.column.getCanSort() && SORTABLE.has(header.column.id)
                    const sorted = header.column.getIsSorted()
                    return (
                      <th
                        key={header.id}
                        scope="col"
                        aria-sort={
                          sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : 'none'
                        }
                        className={cn(
                          'px-3 py-2.5 font-medium whitespace-nowrap',
                          header.column.id === 'title_ja' && STICKY_TITLE + ' bg-muted',
                        )}
                      >
                        {header.isPlaceholder ? null : canSort ? (
                          <button
                            type="button"
                            onClick={header.column.getToggleSortingHandler()}
                            className="hover:text-foreground inline-flex items-center gap-1"
                          >
                            <table.FlexRender header={header} />
                            {sorted === 'asc' ? (
                              <ArrowUp className="size-3" aria-hidden="true" />
                            ) : sorted === 'desc' ? (
                              <ArrowDown className="size-3" aria-hidden="true" />
                            ) : (
                              <ArrowUpDown className="size-3 opacity-50" aria-hidden="true" />
                            )}
                          </button>
                        ) : (
                          <table.FlexRender header={header} />
                        )}
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {isPending
                ? Array.from({ length: 5 }, (_, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td colSpan={columns.length} className="px-3 py-3">
                        <Skeleton className="h-5 w-full" />
                      </td>
                    </tr>
                  ))
                : table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="hover:bg-muted/30 border-b align-top last:border-0">
                      {row.getAllCells().map((cell) => (
                        <td
                          key={cell.id}
                          className={cn(
                            'px-3 py-3',
                            cell.column.id === 'title_ja' && STICKY_TITLE + ' bg-card',
                          )}
                        >
                          <table.FlexRender cell={cell} />
                        </td>
                      ))}
                    </tr>
                  ))}
              {!isPending && total === 0 && (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="text-muted-foreground px-3 py-10 text-center"
                  >
                    条件に合う記事がありません
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-3 text-sm">
        <span aria-live="polite">
          全 {total} 件中 {from}〜{to} 件
        </span>
        <div className="flex items-center gap-2">
          <Select
            value={String(pageSize)}
            onValueChange={(v) => {
              setPageSize(Number(v))
              setPage(1)
            }}
          >
            <SelectTrigger aria-label="1ページの件数" className="w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PAGE_SIZES.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n} 件ずつ
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            前へ
          </Button>
          <span className="tabular-nums">
            {page} / {lastPage}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={page >= lastPage}
            onClick={() => setPage(page + 1)}
          >
            次へ
          </Button>
        </div>
      </div>
    </div>
  )
}
