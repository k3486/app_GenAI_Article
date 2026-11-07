import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-muted-foreground mt-1 text-sm">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed py-16 text-center">
      <Inbox className="text-muted-foreground size-8" aria-hidden="true" />
      <p className="font-medium">{title}</p>
      {description && <p className="text-muted-foreground max-w-md text-sm">{description}</p>}
    </div>
  )
}

export function ErrorNotice({
  message = '読み込めませんでした。時間をおいてもう一度お試しください。',
}) {
  return (
    <p
      role="alert"
      className="border-destructive/40 text-destructive rounded-lg border p-4 text-sm"
    >
      {message}
    </p>
  )
}

export const CARD_GRID = 'grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4'
