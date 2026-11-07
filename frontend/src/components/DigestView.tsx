import { ExternalLink } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { formatMonthDay } from '@/lib/format'
import type { Digest, RelatedArticle } from '@/lib/types'

/** 整理記事。Haiku の推測の段落は「考察」として、事実と見分けられるようにする。 */
export function DigestView({ digest, articles }: { digest: Digest; articles: RelatedArticle[] }) {
  return (
    <div className="space-y-6">
      <section aria-label="3行まとめ" className="bg-accent rounded-lg p-4">
        <h3 className="text-accent-foreground mb-2 text-sm font-semibold">3行まとめ</h3>
        <ol className="space-y-1.5 text-sm leading-relaxed">
          {digest.lead.map((line, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-accent-foreground font-semibold tabular-nums">{i + 1}.</span>
              <span>{line}</span>
            </li>
          ))}
        </ol>
      </section>

      {digest.sections.map((section) => (
        <section key={section.heading}>
          <h3 className="mb-2 text-base font-semibold">{section.heading}</h3>
          <div className="space-y-2">
            {section.paragraphs.map((p, i) =>
              p.inference ? (
                <p
                  key={i}
                  className="border-primary/60 bg-accent/40 border-l-2 border-dashed py-1.5 pl-3 text-sm leading-relaxed"
                >
                  <Badge variant="outline" className="mr-2 align-middle text-xs">
                    考察
                  </Badge>
                  {p.text}
                </p>
              ) : (
                <p key={i} className="text-sm leading-relaxed">
                  {p.text}
                </p>
              ),
            )}
          </div>
        </section>
      ))}

      <section aria-label="URL 一覧">
        <h3 className="mb-2 text-base font-semibold">URL 一覧</h3>
        <ul className="space-y-1.5 text-sm">
          {articles.map((a) => (
            <li key={a.url} className="flex flex-wrap items-baseline gap-x-2">
              <Badge
                variant={a.role === 'representative' ? 'secondary' : 'outline'}
                className="text-xs"
              >
                {a.role === 'representative' ? '代表' : '関連'}
              </Badge>
              <a
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary inline-flex items-center gap-1 break-all underline-offset-2 hover:underline"
              >
                {a.title}
                <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
              </a>
              <span className="text-muted-foreground text-xs">
                {a.source_name}・{formatMonthDay(a.published_at)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <p className="text-muted-foreground text-xs">
        整理：{digest.model_id}。「考察」は記事に書かれていない Haiku の推測です。
      </p>
    </div>
  )
}
