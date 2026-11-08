import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { NotesList } from '@/components/NotesList'
import { createQueryClient } from '@/lib/queryClient'
import type { ChatMessage, ChatState, Note } from '@/lib/types'

import { ChatPanel } from './ChatPanel'

const now = '2026-11-08T01:00:00Z'
const user: ChatMessage = {
  id: 1,
  role: 'user',
  content: '前の質問です',
  tool_log: [],
  cost_usd: 0,
  status: 'ok',
  created_at: now,
}
const answer: ChatMessage = {
  id: 2,
  role: 'assistant',
  content: '記事は〜としています。\n（AI の意見）私は重要だと考えます。',
  tool_log: [{ name: 'search_articles', input: { query: '価格' } }],
  cost_usd: 0.0023,
  status: 'ok',
  created_at: now,
}

type Call = { method: string; path: string; body: unknown }
let calls: Call[] = []
let chat: ChatState
let postReply: () => Response

beforeEach(() => {
  calls = []
  chat = { messages: [user, answer], rounds_used: 1, rounds_limit: 20 }
  postReply = () => Response.json(chat)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = String(input)
      calls.push({ method, path, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (method === 'DELETE') return new Response(null, { status: 204 })
      if (method === 'POST' && path.endsWith('/chat')) return postReply()
      if (method === 'POST' && path.endsWith('/notes')) return Response.json({}, { status: 201 })
      if (path.endsWith('/chat')) return Response.json(chat)
      if (path === '/api/status') return Response.json({})
      throw new Error(`unexpected request: ${method} ${path}`)
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderPanel(notes: Note[] = []) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ChatPanel topicId={7} notes={notes} />
    </QueryClientProvider>,
  )
}

test('履歴・調べたこと・費用・残り回数を出し、AI の意見の行だけを区別する', async () => {
  renderPanel()
  expect(await screen.findByText('前の質問です')).toBeInTheDocument()
  expect(screen.getByText('残り 19 往復')).toBeInTheDocument()
  expect(screen.getByText(/調べたこと：記事を検索「価格」/)).toBeInTheDocument()
  expect(screen.getByText('0.23 セント')).toBeInTheDocument()
  const region = screen.getByRole('region', { name: '壁打ち' })
  expect(within(region).getAllByText('AI の意見')).toHaveLength(1) // 帰属のある行は事実のまま
  expect(screen.getByText('記事は〜としています。')).toBeInTheDocument()
})

test('回答は HTML として描画せず、そのまま文章で表示する', async () => {
  chat.messages = [user, { ...answer, content: '<b>太字</b><script>alert(1)</script>' }]
  renderPanel()
  expect(await screen.findByText('<b>太字</b><script>alert(1)</script>')).toBeInTheDocument()
  expect(document.querySelector('b')).toBeNull()
})

test('質問を送ると待機表示になり、回答が出て入力欄が空になる', async () => {
  const user_ = userEvent.setup()
  postReply = () => {
    chat = {
      messages: [
        ...chat.messages,
        { ...user, id: 3, content: '新しい質問' },
        { ...answer, id: 4, content: '新しい回答です', tool_log: [], cost_usd: 0 },
      ],
      rounds_used: 2,
      rounds_limit: 20,
    }
    return Response.json(chat)
  }
  renderPanel()
  await screen.findByText('前の質問です')
  const box = screen.getByRole('textbox', { name: '質問' })
  await user_.type(box, '新しい質問')
  expect(screen.getByText('5/2000')).toBeInTheDocument()
  await user_.click(screen.getByRole('button', { name: /質問する/ }))
  expect(await screen.findByText('新しい回答です')).toBeInTheDocument()
  expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ question: '新しい質問' })
  expect(box).toHaveValue('')
  expect(screen.getByText('残り 18 往復')).toBeInTheDocument()
})

test('送れないとき（Haiku を使えない等）は、理由を出し、入力は残す', async () => {
  const user_ = userEvent.setup()
  postReply = () =>
    Response.json({ detail: 'Haiku を使えません（LlmUnavailableError）' }, { status: 503 })
  renderPanel()
  await screen.findByText('前の質問です')
  const box = screen.getByRole('textbox', { name: '質問' })
  await user_.type(box, '聞きたいこと')
  await user_.click(screen.getByRole('button', { name: /質問する/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Haiku を使えません')
  expect(box).toHaveValue('聞きたいこと')
})

test('20往復を使い切ると、入力と送信ができない', async () => {
  chat = { messages: [user, answer], rounds_used: 20, rounds_limit: 20 }
  renderPanel()
  expect(await screen.findByText(/この話題の質問は上限に達しました/)).toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: '質問' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /質問する/ })).toBeDisabled()
})

test('空の質問は送れない', async () => {
  renderPanel()
  await screen.findByText('前の質問です')
  expect(screen.getByRole('button', { name: /質問する/ })).toBeDisabled()
})

test('「メモに残す」で回答の本文と元の回答の ID を送る。残した回答は押せない', async () => {
  const user_ = userEvent.setup()
  renderPanel()
  await user_.click(await screen.findByRole('button', { name: /メモに残す/ }))
  await waitFor(() => expect(calls.some((c) => c.path.endsWith('/notes'))).toBe(true))
  expect(calls.find((c) => c.path.endsWith('/notes'))?.body).toEqual({
    text: answer.content,
    chat_message_id: 2,
  })
})

test('すでにメモにした回答は「メモに残しました」で押せない', async () => {
  const saved: Note = { id: 5, topic_id: 7, chat_message_id: 2, text: 'x', created_at: now }
  renderPanel([saved])
  const button = await screen.findByRole('button', { name: /メモに残しました/ })
  expect(button).toBeDisabled()
})

test('メモ一覧: 削除すると DELETE を送る。メモが無ければ何も出さない', async () => {
  const user_ = userEvent.setup()
  const note: Note = {
    id: 5,
    topic_id: 7,
    chat_message_id: null,
    text: 'メモの文章',
    created_at: now,
  }
  const { rerender } = render(
    <QueryClientProvider client={createQueryClient()}>
      <NotesList topicId={7} notes={[note]} />
    </QueryClientProvider>,
  )
  expect(screen.getByText('メモの文章')).toBeInTheDocument()
  await user_.click(screen.getByRole('button', { name: 'このメモを削除' }))
  await waitFor(() => expect(calls.some((c) => c.method === 'DELETE')).toBe(true))
  expect(calls.find((c) => c.method === 'DELETE')?.path).toBe('/api/notes/5')
  rerender(
    <QueryClientProvider client={createQueryClient()}>
      <NotesList topicId={7} notes={[]} />
    </QueryClientProvider>,
  )
  expect(screen.queryByRole('region', { name: 'メモ' })).toBeNull()
})
