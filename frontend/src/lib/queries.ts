/** サーバーのデータを取る・更新するための hooks（TanStack Query）。 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './api'
import type {
  AppStatus,
  ArticleType,
  Category,
  Insights,
  RunSummary,
  Settings,
  SourceInfo,
  TopicCard,
  TopicDetail,
  TopicList,
  TopicStatePatch,
} from './types'

export type TopicView = 'latest' | 'favorites' | 'backlog' | 'all' | 'rejected'
export type SortKey = 'score' | 'published_at' | 'selected_at' | 'title_ja' | 'source_name'

export type TopicsParams = {
  view: TopicView
  q?: string
  type?: ArticleType
  category?: Category
  source?: string
  sort?: SortKey
  order?: 'asc' | 'desc'
  page?: number
  pageSize?: number
}

function toQuery(params: TopicsParams): string {
  const search = new URLSearchParams({ view: params.view })
  if (params.q) search.set('q', params.q)
  if (params.type) search.set('type', params.type)
  if (params.category) search.set('category', params.category)
  if (params.source) search.set('source', params.source)
  if (params.sort) search.set('sort', params.sort)
  if (params.order) search.set('order', params.order)
  if (params.page) search.set('page', String(params.page))
  if (params.pageSize) search.set('page_size', String(params.pageSize))
  return search.toString()
}

export function useTopics(params: TopicsParams) {
  return useQuery({
    queryKey: ['topics', params],
    queryFn: ({ signal }) => apiGet<TopicList>(`/topics?${toQuery(params)}`, { signal }),
    placeholderData: keepPreviousData,
  })
}

export function useTopic(id: number | null) {
  return useQuery({
    queryKey: ['topic', id],
    queryFn: ({ signal }) => apiGet<TopicDetail>(`/topics/${id}`, { signal }),
    enabled: id !== null,
  })
}

/** ★・👍👎・既読などの操作。送ったフィールドだけが変わる。 */
export function usePatchState() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TopicStatePatch }) =>
      apiSend<TopicCard>('PATCH', `/topics/${id}/state`, patch),
    onSuccess: () => {
      // 一覧の所属（お気に入り・バックログ）や分析の指標が変わるので、まとめて取り直す
      void client.invalidateQueries({ queryKey: ['topics'] })
      void client.invalidateQueries({ queryKey: ['topic'] })
      void client.invalidateQueries({ queryKey: ['insights'] })
    },
  })
}

export function useStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: ({ signal }) => apiGet<AppStatus>('/status', { signal }),
    // 更新中だけ、短い間隔で状態を見に行く
    refetchInterval: (query) => (query.state.data?.latest_run?.status === 'running' ? 1500 : false),
  })
}

export function useStartRun() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => apiSend<AppStatus>('POST', '/runs'),
    onSuccess: (status) => client.setQueryData(['status'], status),
  })
}

export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: ({ signal }) => apiGet<RunSummary[]>('/runs', { signal }),
  })
}

export function useInsights() {
  return useQuery({
    queryKey: ['insights'],
    queryFn: ({ signal }) => apiGet<Insights>('/insights', { signal }),
  })
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: ({ signal }) => apiGet<Settings>('/settings', { signal }),
  })
}

export function useSaveSettings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (settings: Settings) => apiSend<Settings>('PUT', '/settings', settings),
    onSuccess: (saved) => {
      client.setQueryData(['settings'], saved)
      void client.invalidateQueries({ queryKey: ['status'] })
    },
  })
}

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: ({ signal }) => apiGet<SourceInfo[]>('/sources', { signal }),
  })
}

export function useToggleSource() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      apiSend<SourceInfo>('PATCH', `/sources/${key}`, { enabled }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['sources'] }),
  })
}
