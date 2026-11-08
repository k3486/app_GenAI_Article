import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { LatestPage } from '@/features/topics/LatestPage'
import { createQueryClient } from '@/lib/queryClient'
import type { PreferenceState, ProfileVersion, Proposal } from '@/lib/types'
import { status } from '@/test-fixtures'

import { PreferenceTab } from './PreferenceTab'
import { ProfileVersions } from './ProfileVersions'
import { ProposalCards } from './ProposalCards'

const now = '2026-11-08T01:00:00Z'
const add: Proposal = {
  id: 1,
  kind: 'add',
  before_text: '',
  after_text: '- ローカルLLMの運用',
  reason: 'ローカルLLMの記事に👍が多いためです',
  evidence: [{ id: 11, title_ja: 'ローカルLLM入門' }],
  status: 'pending',
  applied_text: null,
  created_at: now,
  decided_at: null,
}
const remove: Proposal = {
  ...add,
  id: 2,
  kind: 'remove',
  before_text: '- 暗号資産の話題',
  after_text: '',
  reason: '暗号資産の記事に👎が多いためです',
  evidence: [],
}

type Call = { method: string; path: string; body: unknown }
let calls: Call[] = []
let proposals: Proposal[]
let versions: ProfileVersion[]
let preference: PreferenceState
let failApprove: Response | null
let pendingCount: number

beforeEach(() => {
  calls = []
  proposals = [add, remove]
  versions = [
    { id: 3, text: '現在の文章', source: 'proposal', created_at: now },
    { id: 2, text: '古い文章', source: 'manual', created_at: now },
    { id: 1, text: '最初の文章', source: 'initial', created_at: now },
  ]
  preference = {
    text: '実践的な記事を好みます',
    source: 'haiku',
    updated_at: now,
    feedback_since: 14,
    update_every: 20,
  }
  failApprove = null
  pendingCount = 2
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = String(input)
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (path.startsWith('/api/proposals?')) return Response.json(proposals)
      if (path.endsWith('/approve')) return failApprove ?? Response.json(add)
      if (path.endsWith('/reject')) return Response.json(add)
      if (path === '/api/profile/versions') return Response.json(versions)
      if (path.includes('/restore')) return Response.json(versions[1])
      if (path === '/api/preference' && method === 'PUT') {
        const body = JSON.parse(String(init?.body)) as { text: string }
        preference = { ...preference, text: body.text, source: 'manual', feedback_since: 0 }
        return Response.json(preference)
      }
      if (path === '/api/preference') return Response.json(preference)
      if (path === '/api/status')
        return Response.json({ ...status, pending_proposals: pendingCount })
      if (path.startsWith('/api/topics?'))
        return Response.json({ items: [], total: 0, page: 1, page_size: 100 })
      throw new Error(`unexpected request: ${method} ${path}`)
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function wrap(node: React.ReactNode) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

test('修正案: 種類・変更前→変更後・理由・根拠の記事を出す。0件なら何も出さない', async () => {
  wrap(<ProposalCards locked={false} />)
  expect(await screen.findByText('興味プロファイルの修正案（2件）')).toBeInTheDocument()
  expect(screen.getByText('追加')).toBeInTheDocument()
  expect(screen.getByText('- ローカルLLMの運用')).toBeInTheDocument()
  expect(screen.getByText(/ローカルLLMの記事に👍が多い/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'ローカルLLM入門' })).toBeInTheDocument()
  expect(screen.getByText('（この文を削除）')).toBeInTheDocument() // 削除案の変更後
})

test('修正案が0件のときは、セクションごと出さない', async () => {
  proposals = []
  wrap(<ProposalCards locked={false} />)
  await waitFor(() => expect(calls.length).toBeGreaterThan(0))
  expect(screen.queryByRole('region', { name: 'プロファイルの修正案' })).toBeNull()
})

test('承認: そのまま承認すると、編集なしで送る', async () => {
  const user = userEvent.setup()
  wrap(<ProposalCards locked={false} />)
  const card = (await screen.findByText('- ローカルLLMの運用')).closest('li') as HTMLElement
  await user.click(within(card).getByRole('button', { name: '承認' }))
  await waitFor(() => expect(calls.some((c) => c.path === '/api/proposals/1/approve')).toBe(true))
  expect(calls.find((c) => c.path === '/api/proposals/1/approve')?.body).toEqual({
    edited_text: null,
  })
})

test('編集して承認: 編集した文を送る。削除案には「編集して承認」が無い', async () => {
  const user = userEvent.setup()
  wrap(<ProposalCards locked={false} />)
  const card = (await screen.findByText('- ローカルLLMの運用')).closest('li') as HTMLElement
  await user.click(within(card).getByRole('button', { name: '編集して承認' }))
  const box = within(card).getByRole('textbox', { name: '変更後の文を編集' })
  await user.clear(box)
  await user.type(box, '- 自分の用途に合うローカルLLM')
  await user.click(within(card).getByRole('button', { name: 'この内容で承認' }))
  await waitFor(() => expect(calls.some((c) => c.path === '/api/proposals/1/approve')).toBe(true))
  expect(calls.find((c) => c.path === '/api/proposals/1/approve')?.body).toEqual({
    edited_text: '- 自分の用途に合うローカルLLM',
  })
  const removeCard = screen.getByText('- 暗号資産の話題').closest('li') as HTMLElement
  expect(within(removeCard).queryByRole('button', { name: '編集して承認' })).toBeNull()
})

test('却下: reject を送る', async () => {
  const user = userEvent.setup()
  wrap(<ProposalCards locked={false} />)
  const card = (await screen.findByText('- ローカルLLMの運用')).closest('li') as HTMLElement
  await user.click(within(card).getByRole('button', { name: '却下' }))
  await waitFor(() => expect(calls.some((c) => c.path === '/api/proposals/1/reject')).toBe(true))
})

test('承認できないとき（プロファイルが変わった等）は理由を出す', async () => {
  const user = userEvent.setup()
  failApprove = Response.json(
    { detail: 'プロファイルが変わったため、変更前の文が見つかりません。内容を確認してください' },
    { status: 409 },
  )
  wrap(<ProposalCards locked={false} />)
  const card = (await screen.findByText('- ローカルLLMの運用')).closest('li') as HTMLElement
  await user.click(within(card).getByRole('button', { name: '承認' }))
  expect(await within(card).findByRole('alert')).toHaveTextContent('プロファイルが変わった')
})

test('未保存の変更があるときは、承認できない（上書きを防ぐ）が却下はできる', async () => {
  wrap(<ProposalCards locked />)
  const card = (await screen.findByText('- ローカルLLMの運用')).closest('li') as HTMLElement
  expect(within(card).getByRole('button', { name: '承認' })).toBeDisabled()
  expect(within(card).getByRole('button', { name: '編集して承認' })).toBeDisabled()
  expect(within(card).getByRole('button', { name: '却下' })).toBeEnabled()
  expect(within(card).getByText(/未保存の変更があります/)).toBeInTheDocument()
})

test('好みメモ: 内容と「あと N 件」を出し、直して保存できる', async () => {
  const user = userEvent.setup()
  wrap(<PreferenceTab />)
  const box = await screen.findByRole('textbox', { name: '好みメモ' })
  expect(box).toHaveValue('実践的な記事を好みます')
  expect(screen.getByText(/あと 6 件の評価で/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
  await user.clear(box)
  await user.type(box, '論文より事例が好きです')
  await user.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(calls.some((c) => c.method === 'PUT')).toBe(true))
  expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({ text: '論文より事例が好きです' })
})

test('履歴: 現在の版には戻すボタンが無い。確認してから戻す', async () => {
  const user = userEvent.setup()
  wrap(<ProfileVersions locked={false} />)
  expect(await screen.findByText('現在の版')).toBeInTheDocument()
  const buttons = screen.getAllByRole('button', { name: 'この版に戻す' })
  expect(buttons).toHaveLength(2) // 現在の版を除く
  await user.click(buttons[0]!)
  expect(screen.getByText('この版に戻しますか？')).toBeInTheDocument()
  expect(calls.some((c) => c.path.includes('/restore'))).toBe(false) // まだ戻さない
  await user.click(screen.getByRole('button', { name: '戻す' }))
  await waitFor(() =>
    expect(calls.some((c) => c.path === '/api/profile/versions/2/restore')).toBe(true),
  )
})

test('ホーム: 承認待ちの修正案があると、設定へのリンクを出す。0件なら出さない', async () => {
  wrap(<LatestPage />)
  const link = await screen.findByRole('link', { name: /修正案が 2 件あります/ })
  expect(link).toHaveAttribute('href', '/settings')
})

test('ホーム: 修正案が0件ならリンクを出さない', async () => {
  pendingCount = 0
  wrap(<LatestPage />)
  await screen.findByText('最新トピック')
  await waitFor(() => expect(calls.some((c) => c.path === '/api/status')).toBe(true))
  expect(screen.queryByRole('link', { name: /修正案/ })).toBeNull()
})
