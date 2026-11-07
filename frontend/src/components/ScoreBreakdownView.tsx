import type { ScoreBreakdown } from '@/lib/types'
import { cn } from '@/lib/utils'

function Segments({ score }: { score: number }) {
  return (
    <div className="flex gap-1" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((n) => (
        <span
          key={n}
          className={cn('h-2 w-6 rounded-full sm:w-8', n <= score ? 'bg-primary' : 'bg-border')}
        />
      ))}
    </div>
  )
}

/** 5つの観点の点数（1〜5）と、合計にどれだけ効いたか。 */
export function ScoreBreakdownView({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <section aria-label="点数の内訳" className="bg-card rounded-lg border p-4">
      <ul className="space-y-2.5">
        {breakdown.criteria.map((c) => {
          const points = (c.weight * (c.score - 1)) / 4
          return (
            <li
              key={c.key}
              className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[14rem_auto_1fr]"
            >
              <span className="text-sm">{c.label}</span>
              <Segments score={c.score} />
              <span className="text-muted-foreground col-span-2 text-xs tabular-nums sm:col-span-1 sm:text-right">
                {c.score}/5 ・ 重み {c.weight} → {points.toFixed(1)} 点
              </span>
            </li>
          )
        })}
      </ul>
      <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 border-t pt-3 text-sm">
        <span className="text-muted-foreground">
          {breakdown.official_bonus > 0 && `公式記事の加点 +${breakdown.official_bonus}　`}
        </span>
        <span className="font-semibold">
          合計 <span className="text-lg tabular-nums">{breakdown.total}</span> 点
        </span>
      </div>
      <p className="text-muted-foreground mt-2 text-sm">{breakdown.reason}</p>
    </section>
  )
}
