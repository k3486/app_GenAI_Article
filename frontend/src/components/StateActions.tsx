import { Bookmark, Check, Star, ThumbsDown, ThumbsUp } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { usePatchState } from '@/lib/queries'
import type { TopicCard } from '@/lib/types'
import { cn } from '@/lib/utils'

type Props = {
  topic: Pick<TopicCard, 'id' | 'state' | 'selection'>
  className?: string
}

function ActionButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={label}
          aria-pressed={active}
          onClick={onClick}
          className={cn('size-8', active && 'bg-accent text-accent-foreground')}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

/** ★ 保存 / 👍👎 好みの学習 / 後で読む / 読了。選定された記事用。 */
export function StateActions({ topic, className }: Props) {
  const { mutate } = usePatchState()
  const { state, id } = topic
  const patch = (value: Parameters<typeof mutate>[0]['patch']) => mutate({ id, patch: value })

  return (
    <div className={cn('flex items-center gap-0.5', className)}>
      <ActionButton
        label={state.starred ? 'お気に入りから外す' : 'お気に入りに保存（★）'}
        active={state.starred}
        onClick={() => patch({ starred: !state.starred })}
      >
        <Star className={cn('size-4', state.starred && 'fill-current')} />
      </ActionButton>
      <ActionButton
        label="好み：いい（👍）"
        active={state.rating === 'like'}
        onClick={() => patch({ rating: state.rating === 'like' ? null : 'like' })}
      >
        <ThumbsUp className={cn('size-4', state.rating === 'like' && 'fill-current')} />
      </ActionButton>
      <ActionButton
        label="好み：よくない（👎）"
        active={state.rating === 'dislike'}
        onClick={() => patch({ rating: state.rating === 'dislike' ? null : 'dislike' })}
      >
        <ThumbsDown className={cn('size-4', state.rating === 'dislike' && 'fill-current')} />
      </ActionButton>
      <span aria-hidden="true" className="bg-border mx-1 h-4 w-px" />
      <ActionButton
        label={state.backlog ? '「後で読む」を外す' : '後で読む'}
        active={state.backlog}
        onClick={() => patch({ backlog: !state.backlog })}
      >
        <Bookmark className={cn('size-4', state.backlog && 'fill-current')} />
      </ActionButton>
      <ActionButton
        label={state.read_state === 'read' ? '未読に戻す' : '読んだ'}
        active={state.read_state === 'read'}
        onClick={() => patch({ read_state: state.read_state === 'read' ? 'unread' : 'read' })}
      >
        <Check className="size-4" />
      </ActionButton>
    </div>
  )
}
