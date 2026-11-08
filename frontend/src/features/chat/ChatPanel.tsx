import { BookmarkPlus, Check, Loader2, Send } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { ApiError } from '@/lib/api'
import { useAddNote, useChat, useSendChat } from '@/lib/queries'
import type { ChatMessage, Note } from '@/lib/types'

const QUESTION_MAX = 2000
const AI_OPINION = '（AI の意見）'

const TOOL_LABEL: Record<string, string> = {
  read_article: '記事を読む',
  read_related: '関連記事を読む',
  search_articles: '記事を検索',
  search_favorites: '★の記事を検索',
}

/** 1回の回答の費用は小さいので、セントで表示する（$0.00 になってしまわないように）。 */
function formatCost(usd: number): string {
  return usd < 0.01 ? `${(usd * 100).toFixed(2)} セント` : `$${usd.toFixed(3)}`
}

function toolText(call: ChatMessage['tool_log'][number]): string {
  const label = TOOL_LABEL[String(call.name)] ?? String(call.name)
  const input = call.input as Record<string, unknown> | undefined
  const query = typeof input?.query === 'string' ? `「${input.query}」` : ''
  return `${label}${query}`
}

/** 回答の本文。「（AI の意見）」で始まる行は、事実と見分けられるように色を変える。 */
function AnswerText({ text }: { text: string }) {
  return (
    <div className="space-y-2">
      {text
        .split('\n')
        .filter((line) => line.trim() !== '')
        .map((line, i) =>
          line.startsWith(AI_OPINION) ? (
            <p
              key={i}
              className="border-primary/60 bg-accent/40 border-l-2 border-dashed py-1.5 pl-3 text-sm leading-relaxed"
            >
              <Badge variant="outline" className="mr-2 align-middle text-xs">
                AI の意見
              </Badge>
              {line.slice(AI_OPINION.length).trimStart()}
            </p>
          ) : (
            <p key={i} className="text-sm leading-relaxed">
              {line}
            </p>
          ),
        )}
    </div>
  )
}

function Answer({
  message,
  topicId,
  saved,
}: {
  message: ChatMessage
  topicId: number
  saved: boolean
}) {
  const add = useAddNote(topicId)
  return (
    <div className="bg-card space-y-2 rounded-lg border p-3">
      <AnswerText text={message.content} />
      {message.status === 'limited' && (
        <p className="text-status-warning text-xs">費用の上限に達したため、回答できませんでした</p>
      )}
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
        {message.tool_log.length > 0 && (
          <span>調べたこと：{message.tool_log.map(toolText).join('、')}</span>
        )}
        {message.cost_usd > 0 && <span>{formatCost(message.cost_usd)}</span>}
        {message.status === 'ok' && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto h-7 gap-1 px-2 text-xs"
            disabled={saved || add.isPending}
            onClick={() => add.mutate({ text: message.content, chat_message_id: message.id })}
          >
            {saved ? (
              <Check className="size-3.5" aria-hidden="true" />
            ) : (
              <BookmarkPlus className="size-3.5" aria-hidden="true" />
            )}
            {saved ? 'メモに残しました' : 'メモに残す'}
          </Button>
        )}
      </div>
    </div>
  )
}

/** 壁打ち: 整理記事を読んで気になったことを、Haiku に質問する。回答はただの文章として表示する。 */
export function ChatPanel({ topicId, notes }: { topicId: number; notes: Note[] }) {
  const { data, isPending, isError } = useChat(topicId)
  const send = useSendChat(topicId)
  const [question, setQuestion] = useState('')

  const savedIds = new Set(notes.map((n) => n.chat_message_id))
  const remaining = data ? data.rounds_limit - data.rounds_used : 0
  const canSend = question.trim() !== '' && !send.isPending && remaining > 0

  function submit() {
    if (!canSend) return
    const text = question.trim()
    send.mutate(text, { onSuccess: () => setQuestion('') })
  }

  return (
    <section aria-label="壁打ち" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">壁打ち（AI に質問する）</h3>
        {data && <span className="text-muted-foreground text-xs">残り {remaining} 往復</span>}
      </div>

      {isPending && <Skeleton className="h-16 w-full" />}
      {isError && <p className="text-destructive text-sm">会話を読み込めませんでした</p>}

      {data && data.messages.length > 0 && (
        <ol className="space-y-3">
          {data.messages.map((m) => (
            <li key={m.id}>
              {m.role === 'user' ? (
                <p className="bg-accent/60 ml-auto w-fit max-w-[90%] rounded-lg px-3 py-2 text-sm leading-relaxed break-words whitespace-pre-wrap">
                  {m.content}
                </p>
              ) : (
                <Answer message={m} topicId={topicId} saved={savedIds.has(m.id)} />
              )}
            </li>
          ))}
        </ol>
      )}

      {send.isPending && (
        <p role="status" className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          考えています…（数秒〜十数秒かかります）
        </p>
      )}
      {send.isError && (
        <p role="alert" className="text-destructive text-sm">
          質問を送れませんでした：
          {send.error instanceof ApiError && send.error.detail
            ? send.error.detail
            : '時間をおいてもう一度お試しください'}
        </p>
      )}

      <div className="space-y-2">
        <Textarea
          aria-label="質問"
          placeholder="この記事について聞きたいことを書いてください（過去の記事との比較も聞けます）"
          value={question}
          maxLength={QUESTION_MAX}
          disabled={send.isPending || remaining <= 0}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submit()
          }}
        />
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted-foreground text-xs tabular-nums">
            {question.length}/{QUESTION_MAX}
            {remaining <= 0 && '　この話題の質問は上限に達しました'}
          </span>
          <Button type="button" size="sm" disabled={!canSend} onClick={submit}>
            <Send className="size-4" aria-hidden="true" />
            質問する
          </Button>
        </div>
      </div>
    </section>
  )
}
