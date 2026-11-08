import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { formatDateTime } from '@/lib/format'
import { usePreference, useSavePreference } from '@/lib/queries'

const MEMO_MAX = 800
const SOURCE_LABEL = { haiku: 'AI が作成', manual: 'あなたが編集', none: '' }

/** 好みメモ: 👍/👎の傾向を AI がまとめたもの。採点のときに参考にされる。自分で直せる。 */
export function PreferenceTab() {
  const { data, isPending, isError } = usePreference()
  const save = useSavePreference()
  const [draft, setDraft] = useState<string | null>(null)

  if (isPending) return <Skeleton className="h-48 rounded-xl" />
  if (isError || !data) return <p className="text-destructive text-sm">読み込めませんでした</p>

  const text = draft ?? data.text
  const remaining = Math.max(0, data.update_every - data.feedback_since)

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-base font-semibold">好みメモ</h2>
        <p className="text-muted-foreground mt-1 text-sm">
          あなたの👍・👎・「実はよかった」から、AI
          が読み取った好みの傾向です。採点のときに、興味プロファイルと一緒に参考にされます。内容が違うと感じたら、直してください。
        </p>
      </div>
      <Textarea
        aria-label="好みメモ"
        value={text}
        rows={10}
        maxLength={MEMO_MAX}
        placeholder="まだありません。評価が貯まると、更新の最後に AI が作ります"
        onChange={(e) => setDraft(e.target.value)}
        className="leading-relaxed"
      />
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-muted-foreground text-xs tabular-nums">
          {text.length}/{MEMO_MAX}
          {data.updated_at &&
            `　${formatDateTime(data.updated_at)}更新（${SOURCE_LABEL[data.source]}）`}
        </span>
        <span className="text-muted-foreground text-xs">
          {remaining > 0
            ? `あと ${remaining} 件の評価で、次の更新時に自動で作り直します`
            : '評価が貯まったので、次の更新で作り直します'}
        </span>
        <div className="ml-auto flex gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={draft === null}
            onClick={() => setDraft(null)}
          >
            変更を破棄
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={draft === null || save.isPending}
            onClick={() => save.mutate(text, { onSuccess: () => setDraft(null) })}
          >
            保存
          </Button>
        </div>
      </div>
      {save.isError && (
        <p role="alert" className="text-destructive text-sm">
          保存できませんでした
        </p>
      )}
    </div>
  )
}
