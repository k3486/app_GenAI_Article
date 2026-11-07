import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/** 開いている話題の詳細。URL の `?topic=ID` で持つので、どのシートからでも開け、戻るボタンで閉じられる。 */
export function useTopicParam() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('topic')
  const topicId = raw !== null && /^\d+$/.test(raw) ? Number(raw) : null

  const open = useCallback(
    (id: number) =>
      setParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('topic', String(id))
        return next
      }),
    [setParams],
  )
  const close = useCallback(
    () =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.delete('topic')
          return next
        },
        { replace: true },
      ),
    [setParams],
  )
  return { topicId, open, close }
}
