import {
  Bot,
  Briefcase,
  Cpu,
  Lightbulb,
  Newspaper,
  ShieldCheck,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react'

import type { Category } from '@/lib/types'
import { cn } from '@/lib/utils'

const ART: Record<Category, { icon: LucideIcon; color: string }> = {
  dev_tools_agents: { icon: Bot, color: 'var(--viz-1)' },
  models: { icon: Cpu, color: 'var(--viz-2)' },
  use_cases: { icon: Briefcase, color: 'var(--viz-3)' },
  know_how: { icon: Lightbulb, color: 'var(--viz-4)' },
  regulation_safety: { icon: ShieldCheck, color: 'var(--viz-5)' },
  industry_trends: { icon: TrendingUp, color: 'var(--viz-6)' },
  other: { icon: Newspaper, color: 'var(--viz-other)' },
}

/** 記事の代表画像。画像が無い記事は、カテゴリの色とアイコンの絵を出す。 */
export function ThumbArt({
  imageUrl,
  category,
  className,
}: {
  imageUrl: string | null
  category: Category
  className?: string
}) {
  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt=""
        loading="lazy"
        className={cn('size-full object-cover', className)}
      />
    )
  }
  const { icon: Icon, color } = ART[category]
  return (
    <div
      aria-hidden="true"
      className={cn('flex size-full items-center justify-center', className)}
      style={{
        background: `linear-gradient(135deg, color-mix(in oklab, ${color} 26%, var(--card)), color-mix(in oklab, ${color} 7%, var(--card)))`,
      }}
    >
      <Icon className="size-10 opacity-60" style={{ color }} strokeWidth={1.5} />
    </div>
  )
}
