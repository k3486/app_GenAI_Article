import { Badge } from '@/components/ui/badge'
import { SOURCE_KIND_LABEL } from '@/lib/labels'
import type { Insights } from '@/lib/types'

/** 情報源の成績：候補のうち何割が選ばれたか（棒）と、👍👎・平均点。入れ替えの判断材料。 */
export function SourceStatsTable({ sources }: { sources: Insights['sources'] }) {
  const rows = [...sources].sort((a, b) => (b.avg_score ?? 0) - (a.avg_score ?? 0))
  return (
    <section className="bg-card rounded-xl border p-4 sm:p-5">
      <h2 className="text-base font-semibold">情報源の成績</h2>
      <p className="text-muted-foreground mt-0.5 mb-3 text-xs">
        棒は「集めた候補のうち選ばれた割合」です。平均点の高い順に並びます。
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-muted-foreground border-b text-left text-xs">
            <tr>
              <th scope="col" className="px-2 py-2 font-medium">
                情報源
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                種別
              </th>
              <th scope="col" className="px-2 py-2 text-right font-medium">
                候補
              </th>
              <th scope="col" className="px-2 py-2 font-medium">
                選ばれた割合
              </th>
              <th scope="col" className="px-2 py-2 text-right font-medium">
                👍
              </th>
              <th scope="col" className="px-2 py-2 text-right font-medium">
                👎
              </th>
              <th scope="col" className="px-2 py-2 text-right font-medium">
                平均点
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const rate = s.candidates === 0 ? 0 : s.selected / s.candidates
              return (
                <tr key={s.source_name} className="border-b last:border-0">
                  <td className="px-2 py-2 font-medium">{s.source_name}</td>
                  <td className="px-2 py-2">
                    <Badge variant="outline">{SOURCE_KIND_LABEL[s.kind]}</Badge>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{s.candidates}</td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="bg-border h-2 w-28 overflow-hidden rounded-full"
                        aria-hidden="true"
                      >
                        <span
                          className="bg-primary block h-full rounded-full"
                          style={{ width: `${rate * 100}%` }}
                        />
                      </span>
                      <span className="text-muted-foreground text-xs tabular-nums">
                        {s.selected}/{s.candidates}（{Math.round(rate * 100)}%）
                      </span>
                    </div>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{s.likes}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{s.dislikes}</td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {s.avg_score === null ? '—' : s.avg_score.toFixed(1)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
