import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import { useProfileVersions, useRestoreVersion } from '@/lib/queries'
import type { ProfileVersion } from '@/lib/types'

const SOURCE_LABEL: Record<ProfileVersion['source'], string> = {
  initial: '最初の版',
  manual: '手で編集',
  proposal: '修正案を承認',
  restore: '履歴から戻した',
}

/** 興味プロファイルの履歴。古い版に戻せる（戻した結果も、新しい版として残る）。 */
export function ProfileVersions({ locked }: { locked: boolean }) {
  const { data } = useProfileVersions()
  const restore = useRestoreVersion()
  const [confirming, setConfirming] = useState<number | null>(null)
  if (!data || data.length === 0) return null

  return (
    <section aria-label="プロファイルの履歴" className="mt-8 space-y-2">
      <h3 className="text-base font-semibold">プロファイルの履歴</h3>
      {locked && (
        <p className="text-status-warning text-xs">
          未保存の変更があります。保存または破棄してから、戻してください
        </p>
      )}
      <ul className="space-y-2">
        {data.map((v, index) => (
          <li key={v.id} className="bg-card space-y-2 rounded-lg border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {index === 0 ? '現在の版' : formatDateTime(v.created_at)}
              </span>
              <span className="text-muted-foreground text-xs">
                {index === 0 && `${formatDateTime(v.created_at)}・`}
                {SOURCE_LABEL[v.source]}・{v.text.length} 文字
              </span>
              {index > 0 &&
                (confirming === v.id ? (
                  <span className="ml-auto flex items-center gap-2">
                    <span className="text-xs">この版に戻しますか？</span>
                    <Button
                      type="button"
                      size="sm"
                      disabled={locked || restore.isPending}
                      onClick={() => restore.mutate(v.id, { onSuccess: () => setConfirming(null) })}
                    >
                      戻す
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setConfirming(null)}
                    >
                      やめる
                    </Button>
                  </span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    onClick={() => setConfirming(v.id)}
                  >
                    この版に戻す
                  </Button>
                ))}
            </div>
            <details>
              <summary className="text-muted-foreground cursor-pointer text-xs">内容を見る</summary>
              <pre className="mt-2 max-h-60 overflow-auto text-xs leading-relaxed whitespace-pre-wrap">
                {v.text}
              </pre>
            </details>
          </li>
        ))}
      </ul>
      {restore.isError && (
        <p role="alert" className="text-destructive text-sm">
          戻せませんでした
        </p>
      )}
    </section>
  )
}
