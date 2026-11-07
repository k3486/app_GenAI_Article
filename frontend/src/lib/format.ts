/** 日付の表示。サーバーは UTC で返すので、表示のときだけ日本時間にする。 */
const TZ = 'Asia/Tokyo'

const monthDay = new Intl.DateTimeFormat('ja-JP', {
  timeZone: TZ,
  month: 'numeric',
  day: 'numeric',
})
const monthDayTime = new Intl.DateTimeFormat('ja-JP', {
  timeZone: TZ,
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})
const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: TZ })

export function formatMonthDay(iso: string): string {
  return monthDay.format(new Date(iso))
}

export function formatDateTime(iso: string): string {
  return monthDayTime.format(new Date(iso))
}

/** 日本時間の日付キー（YYYY-MM-DD） */
export function jstDateKey(iso: string | Date): string {
  return ymd.format(typeof iso === 'string' ? new Date(iso) : iso)
}

/** 「今日の更新」「昨日の更新」「11/5 の更新」 */
export function runDayLabel(iso: string, now: Date = new Date()): string {
  const key = jstDateKey(iso)
  const today = jstDateKey(now)
  const yesterday = jstDateKey(new Date(now.getTime() - 24 * 60 * 60 * 1000))
  if (key === today) return '今日の更新'
  if (key === yesterday) return '昨日の更新'
  return `${formatMonthDay(iso)} の更新`
}

export function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`
}

export function formatPercent(value: number | null | undefined): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}
