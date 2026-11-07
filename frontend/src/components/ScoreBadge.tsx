import { cn } from '@/lib/utils'

type Band = 'high' | 'mid' | 'low' | 'none'

function bandOf(score: number): Band {
  if (score >= 80) return 'high'
  if (score >= 70) return 'mid'
  if (score >= 60) return 'low'
  return 'none'
}

const BAND_CLASS: Record<Band, string> = {
  high: 'bg-score-high text-score-high-fg',
  mid: 'bg-score-mid text-score-mid-fg',
  low: 'bg-score-low text-score-low-fg',
  none: 'bg-score-none text-score-none-fg',
}

/** 点数を、60 / 70 / 80 点の帯で濃さを変えて見せる。色だけに頼らず数字も必ず出す。 */
export function ScoreBadge({ score, className }: { score: number; className?: string }) {
  return (
    <span
      role="img"
      aria-label={`点数 ${score}`}
      className={cn(
        'inline-flex min-w-9 items-center justify-center rounded-full px-2 py-0.5 text-sm font-semibold tabular-nums',
        BAND_CLASS[bandOf(score)],
        className,
      )}
    >
      {score}
    </span>
  )
}
