import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { AppRoutes } from './App'
import { createQueryClient } from './lib/queryClient'
import { TooltipProvider } from './components/ui/tooltip'
import { insights, makeCard, makeDetail, settings, sources, status } from './test-fixtures'

type Call = { method: string; path: string; body: unknown }
let calls: Call[] = []

const major = makeCard({
  id: 2,
  title_ja: '重大ニュースの記事',
  selection: 'major',
  score: 36,
  run_id: 3,
})
const yesterday = makeCard({
  id: 3,
  title_ja: '昨日の記事',
  run_id: 2,
  score: 70,
  selected_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
})
const today = makeCard({ id: 1, title_ja: '今日の記事', run_id: 3 })
const rejected = makeCard({
  id: 9,
  title_ja: '落選した記事',
  selection: 'rejected',
  score: 21,
  rejection_reason: '関心が低いため落選',
  summary_5lines: ['要約1', '要約2', '要約3', '要約4', '要約5'],
})

function respond(method: string, url: string): unknown {
  const u = new URL(url, 'http://localhost')
  const view = u.searchParams.get('view')
  if (u.pathname === '/api/status') return status
  if (u.pathname === '/api/topics' && method === 'GET') {
    const items =
      view === 'rejected' ? [rejected] : view === 'favorites' ? [] : [today, major, yesterday]
    return { items, total: items.length, page: 1, page_size: 50 }
  }
  if (u.pathname === '/api/topics/1') return makeDetail()
  if (u.pathname === '/api/topics/1/chat') return { messages: [], rounds_used: 0, rounds_limit: 20 }
  if (u.pathname === '/api/proposals') return []
  if (u.pathname === '/api/profile/versions') return []
  if (u.pathname.endsWith('/state')) return makeCard()
  if (u.pathname === '/api/sources') return sources
  if (u.pathname === '/api/insights') return insights
  if (u.pathname === '/api/settings') return settings
  if (u.pathname === '/api/runs') return [status.latest_run]
  throw new Error(`unexpected request: ${method} ${url}`)
}

beforeEach(() => {
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({
        method,
        path: url,
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      })
      if (method === 'POST' && url === '/api/runs') {
        return Response.json({ detail: '更新処理はまだ実装されていません' }, { status: 501 })
      }
      return Response.json(respond(method, url))
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderApp(path = '/') {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

test('最新トピック: 更新の回ごとに区切り、重大ニュースを別枠で出す', async () => {
  renderApp()
  expect(await screen.findByRole('heading', { name: /今日の更新/ })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: /昨日の更新/ })).toBeInTheDocument()
  const majorSection = screen.getByRole('region', { name: /重大ニュース/ })
  expect(within(majorSection).getByText('重大ニュースの記事')).toBeInTheDocument()
  // 試しのデータの注意書きと、前回の更新結果
  expect(screen.getByText(/試しのデータで表示しています/)).toBeInTheDocument()
  expect(screen.getByText(/前回の更新：成功/)).toBeInTheDocument()
  expect(screen.getByText(/モデル変更：claude-haiku-4-5 → claude-haiku-5-5/)).toBeInTheDocument()
})

test('カードを開くと整理記事が出て、AI の意見の段落は「AI の意見」と区別される', async () => {
  const user = userEvent.setup()
  renderApp()
  await user.click(await screen.findByRole('button', { name: '今日の記事 の詳細を開く' }))
  const dialog = await screen.findByRole('dialog')
  expect(await within(dialog).findByText('3行まとめ')).toBeInTheDocument()
  expect(within(dialog).getByText('事実の段落です。')).toBeInTheDocument()
  expect(within(dialog).getAllByText('AI の意見')).toHaveLength(1)
  const breakdown = within(dialog).getByRole('region', { name: '点数の内訳' })
  const urls = within(dialog).getByRole('region', { name: 'URL 一覧' })
  // 点数の内訳は、URL 一覧よりも下（ダイアログの一番下）に出す
  expect(urls.compareDocumentPosition(breakdown) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(within(dialog).getByRole('link', { name: /元の記事を開く/ })).toHaveAttribute(
    'rel',
    'noopener noreferrer',
  )
})

test('★を押すと、送った項目だけを更新する', async () => {
  const user = userEvent.setup()
  renderApp()
  const [star] = await screen.findAllByRole('button', { name: 'お気に入りに保存（★）' })
  await user.click(star!)
  await waitFor(() => expect(calls.some((c) => c.method === 'PATCH')).toBe(true))
  const patch = calls.find((c) => c.method === 'PATCH')!
  expect(patch.path).toMatch(/\/api\/topics\/\d+\/state$/)
  expect(patch.body).toEqual({ starred: true })
})

test('全記事: 表の見出しと、並べ替えの操作', async () => {
  const user = userEvent.setup()
  renderApp('/articles')
  expect(await screen.findByRole('columnheader', { name: /日本語タイトル/ })).toBeInTheDocument()
  expect(screen.getByRole('columnheader', { name: '1行要約' })).toBeInTheDocument()
  expect(screen.getByRole('columnheader', { name: 'URL' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /点数/ }))
  await waitFor(() =>
    expect(calls.some((c) => c.path.includes('sort=score') && c.path.includes('order='))).toBe(
      true,
    ),
  )
})

test('落選記事: 理由と「実はよかった」を出す', async () => {
  const user = userEvent.setup()
  renderApp('/rejected')
  expect(await screen.findByText('落選した記事')).toBeInTheDocument()
  expect(screen.getByText('関心が低いため落選')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '実はよかった' }))
  await waitFor(() =>
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ missed: true }),
  )
})

test('設定: 重みの合計が100でないと保存できない', async () => {
  const user = userEvent.setup()
  renderApp('/settings')
  await user.click(await screen.findByRole('tab', { name: '採点と選定' }))
  const input = await screen.findByLabelText('関心との一致')
  await user.clear(input)
  await user.type(input, '30')
  expect(await screen.findByRole('alert')).toHaveTextContent('100 にしてください')
  expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
})

test('分析: グラフと同じ数字を表でも見られる', async () => {
  const user = userEvent.setup()
  renderApp('/insights')
  const card = (await screen.findByRole('heading', { name: 'トピックの内訳' })).closest('section')!
  await user.click(within(card).getByRole('button', { name: '表' }))
  expect(within(card).getByRole('table')).toBeInTheDocument()
  expect(within(card).getByText('活用ノウハウ')).toBeInTheDocument()
  expect(await screen.findByRole('heading', { name: '情報源の成績' })).toBeInTheDocument()
})

test('更新ボタンが断られたら、サーバーが返した理由を画面に出す', async () => {
  const user = userEvent.setup()
  renderApp()
  await user.click(await screen.findByRole('button', { name: '更新' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(
    '更新を始められませんでした：更新処理はまだ実装されていません',
  )
})
