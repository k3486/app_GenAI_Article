import { ArrowRight } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ApiError } from '@/lib/api'
import { useApproveProposal, usePendingProposals, useRejectProposal } from '@/lib/queries'
import type { Proposal } from '@/lib/types'
import { useTopicParam } from '@/lib/useTopicParam'

const KIND_LABEL: Record<Proposal['kind'], string> = {
  add: '追加',
  remove: '削除',
  rephrase: '言い換え',
}

function errorText(error: unknown): string {
  return error instanceof ApiError && error.detail
    ? error.detail
    : '時間をおいてもう一度お試しください'
}

function Side({ title, text, empty }: { title: string; text: string; empty: string }) {
  return (
    <div className="bg-muted/40 min-w-0 flex-1 rounded-md border p-3">
      <p className="text-muted-foreground mb-1 text-xs">{title}</p>
      <p className="text-sm leading-relaxed break-words whitespace-pre-wrap">
        {text || <span className="text-muted-foreground">{empty}</span>}
      </p>
    </div>
  )
}

function ProposalCard({ proposal, locked }: { proposal: Proposal; locked: boolean }) {
  const approve = useApproveProposal()
  const reject = useRejectProposal()
  const { open } = useTopicParam()
  const [editing, setEditing] = useState(false)
  const [edited, setEdited] = useState(proposal.after_text)
  const busy = approve.isPending || reject.isPending
  const failure = approve.error ?? reject.error

  return (
    <li className="bg-card space-y-3 rounded-lg border p-4">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">{KIND_LABEL[proposal.kind]}</Badge>
        <span className="text-muted-foreground text-xs">
          AI からの提案です。承認するまで反映されません
        </span>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <Side title="現在" text={proposal.before_text} empty="（なし）" />
        <ArrowRight
          className="text-muted-foreground size-4 shrink-0 rotate-90 self-center sm:rotate-0"
          aria-hidden="true"
        />
        {editing ? (
          <div className="min-w-0 flex-1">
            <Textarea
              aria-label="変更後の文を編集"
              value={edited}
              onChange={(e) => setEdited(e.target.value)}
              rows={3}
            />
          </div>
        ) : (
          <Side title="変更後" text={proposal.after_text} empty="（この文を削除）" />
        )}
      </div>
      <p className="text-sm leading-relaxed">
        <span className="text-muted-foreground">理由：</span>
        {proposal.reason}
      </p>
      {proposal.evidence.length > 0 && (
        <p className="text-sm">
          <span className="text-muted-foreground">根拠にした記事：</span>
          {proposal.evidence.map((e, i) => (
            <span key={e.id}>
              {i > 0 && '、'}
              <button
                type="button"
                className="text-primary underline-offset-2 hover:underline"
                onClick={() => open(e.id)}
              >
                {e.title_ja}
              </button>
            </span>
          ))}
        </p>
      )}
      {locked && (
        <p className="text-status-warning text-xs">
          未保存の変更があります。保存または破棄してから、承認してください
        </p>
      )}
      {failure && (
        <p role="alert" className="text-destructive text-sm">
          {errorText(failure)}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {editing ? (
          <>
            <Button
              type="button"
              size="sm"
              disabled={busy || locked || edited.trim() === ''}
              onClick={() => approve.mutate({ id: proposal.id, editedText: edited })}
            >
              この内容で承認
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
              編集をやめる
            </Button>
          </>
        ) : (
          <>
            <Button
              type="button"
              size="sm"
              disabled={busy || locked}
              onClick={() => approve.mutate({ id: proposal.id })}
            >
              承認
            </Button>
            {proposal.kind !== 'remove' && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy || locked}
                onClick={() => setEditing(true)}
              >
                編集して承認
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => reject.mutate(proposal.id)}
            >
              却下
            </Button>
          </>
        )}
      </div>
    </li>
  )
}

/** 興味プロファイルの修正案。0件のときは何も出さない。 */
export function ProposalCards({ locked }: { locked: boolean }) {
  const { data } = usePendingProposals()
  if (!data || data.length === 0) return null
  return (
    <section aria-label="プロファイルの修正案" className="mb-6 space-y-3">
      <h2 className="text-lg font-semibold">興味プロファイルの修正案（{data.length}件）</h2>
      <ul className="space-y-3">
        {data.map((p) => (
          <ProposalCard key={p.id} proposal={p} locked={locked} />
        ))}
      </ul>
    </section>
  )
}
