/** サーバーのデータを取る・更新するための hooks（TanStack Query）。 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiGet, apiSend } from './api'
import type {
  AppStatus,
  ArticleType,
  Category,
  ChatState,
  Insights,
  Note,
  PreferenceState,
  ProfileVersion,
  Proposal,
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

/** 壁打ち（話題ごとの Haiku との会話）。 */
export function useChat(topicId: number) {
  return useQuery({
    queryKey: ['chat', topicId],
    queryFn: ({ signal }) => apiGet<ChatState>(`/topics/${topicId}/chat`, { signal }),
  })
}

export function useSendChat(topicId: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (question: string) =>
      apiSend<ChatState>('POST', `/topics/${topicId}/chat`, { question }),
    onSuccess: (state) => {
      client.setQueryData(['chat', topicId], state)
      void client.invalidateQueries({ queryKey: ['status'] }) // 今月の費用が増える
    },
  })
}

export function useAddNote(topicId: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (note: { text: string; chat_message_id?: number }) =>
      apiSend<Note>('POST', `/topics/${topicId}/notes`, note),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['topic', topicId] }),
  })
}

export function useDeleteNote(topicId: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (noteId: number) => apiSend<undefined>('DELETE', `/notes/${noteId}`),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['topic', topicId] }),
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

/** 好みメモ・興味プロファイルの修正案・プロファイルの履歴。 */
export function usePreference() {
  return useQuery({
    queryKey: ['preference'],
    queryFn: ({ signal }) => apiGet<PreferenceState>('/preference', { signal }),
  })
}

export function useSavePreference() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => apiSend<PreferenceState>('PUT', '/preference', { text }),
    onSuccess: (state) => client.setQueryData(['preference'], state),
  })
}

export function usePendingProposals() {
  return useQuery({
    queryKey: ['proposals', 'pending'],
    queryFn: ({ signal }) => apiGet<Proposal[]>('/proposals?status=pending', { signal }),
  })
}

/** 承認・却下のあとは、修正案・プロファイル・履歴・ホームのバッジをまとめて取り直す。 */
function useRefreshAfterDecision() {
  const client = useQueryClient()
  return () => {
    for (const key of ['proposals', 'settings', 'profile-versions', 'status']) {
      void client.invalidateQueries({ queryKey: [key] })
    }
  }
}

export function useApproveProposal() {
  const refresh = useRefreshAfterDecision()
  return useMutation({
    mutationFn: ({ id, editedText }: { id: number; editedText?: string }) =>
      apiSend<Proposal>('POST', `/proposals/${id}/approve`, { edited_text: editedText ?? null }),
    onSuccess: refresh,
  })
}

export function useRejectProposal() {
  const refresh = useRefreshAfterDecision()
  return useMutation({
    mutationFn: (id: number) => apiSend<Proposal>('POST', `/proposals/${id}/reject`),
    onSuccess: refresh,
  })
}

export function useProfileVersions() {
  return useQuery({
    queryKey: ['profile-versions'],
    queryFn: ({ signal }) => apiGet<ProfileVersion[]>('/profile/versions', { signal }),
  })
}

export function useRestoreVersion() {
  const refresh = useRefreshAfterDecision()
  return useMutation({
    mutationFn: (id: number) => apiSend<ProfileVersion>('POST', `/profile/versions/${id}/restore`),
    onSuccess: refresh,
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
