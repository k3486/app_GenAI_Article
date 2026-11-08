import { Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import { useDeleteNote } from '@/lib/queries'
import type { Note } from '@/lib/types'

/** 整理記事の下に残したメモ（壁打ちの回答から、または手で書いたもの）。 */
export function NotesList({ topicId, notes }: { topicId: number; notes: Note[] }) {
  const remove = useDeleteNote(topicId)
  if (notes.length === 0) return null
  return (
    <section aria-label="メモ" className="space-y-2">
      <h3 className="text-base font-semibold">メモ</h3>
      <ul className="space-y-2">
        {notes.map((note) => (
          <li
            key={note.id}
            className="bg-card flex items-start gap-3 rounded-lg border p-3 text-sm leading-relaxed"
          >
            <div className="min-w-0 flex-1">
              <p className="break-words whitespace-pre-wrap">{note.text}</p>
              <p className="text-muted-foreground mt-1 text-xs">
                {formatDateTime(note.created_at)}
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="このメモを削除"
              disabled={remove.isPending}
              onClick={() => remove.mutate(note.id)}
            >
              <Trash2 className="size-4" aria-hidden="true" />
            </Button>
          </li>
        ))}
      </ul>
    </section>
  )
}
