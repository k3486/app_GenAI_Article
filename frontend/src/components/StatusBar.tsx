import { useQueryClient } from '@tanstack/react-query'
import {
  CircleAlert,
  CircleCheck,
  CircleX,
  LoaderCircle,
  Monitor,
  Moon,
  RefreshCw,
  Sun,
  TriangleAlert,
} from 'lucide-react'
import { useEffect, useRef } from 'react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ApiError } from '@/lib/api'
import { formatDateTime, formatUsd } from '@/lib/format'
import { RUN_STATUS_LABEL } from '@/lib/labels'
import { useStartRun, useStatus } from '@/lib/queries'
import { useTheme, type ThemeMode } from '@/lib/theme'
import type { RunStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const STATUS_ICON: Record<RunStatus, { icon: typeof CircleCheck; className: string }> = {
  running: { icon: LoaderCircle, className: 'animate-spin text-primary' },
  succeeded: { icon: CircleCheck, className: 'text-status-good' },
  partial: { icon: TriangleAlert, className: 'text-status-warning' },
  budget_stopped: { icon: CircleAlert, className: 'text-status-warning' },
  failed: { icon: CircleX, className: 'text-status-critical' },
}

const THEME_ICON: Record<ThemeMode, typeof Sun> = { system: Monitor, light: Sun, dark: Moon }
const THEME_LABEL: Record<ThemeMode, string> = {
  system: '端末の設定に合わせる',
  light: 'ライト',
  dark: 'ダーク',
}
const THEME_NEXT: Record<ThemeMode, ThemeMode> = { system: 'light', light: 'dark', dark: 'system' }

function ThemeToggle() {
  const [mode, setMode] = useTheme()
  const Icon = THEME_ICON[mode]
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={`表示の明るさ：${THEME_LABEL[mode]}（押すと切り替え）`}
          onClick={() => setMode(THEME_NEXT[mode])}
        >
          <Icon className="size-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>表示：{THEME_LABEL[mode]}</TooltipContent>
    </Tooltip>
  )
}

/** 画面の上部：前回の更新結果・今月の費用・更新ボタン。 */
export function StatusBar() {
  const { data } = useStatus()
  const start = useStartRun()
  const client = useQueryClient()
  const run = data?.latest_run ?? null
  const running = run?.status === 'running'

  // 更新が終わったら、一覧・分析・実行履歴を取り直す
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !running) {
      for (const key of ['topics', 'topic', 'insights', 'runs', 'sources']) {
        void client.invalidateQueries({ queryKey: [key] })
      }
    }
    wasRunning.current = running
  }, [running, client])

  const budget = data?.budget
  const ratio = budget ? Math.min(budget.month_cost_usd / budget.month_limit_usd, 1) : 0
  const Icon = run ? STATUS_ICON[run.status].icon : CircleCheck

  return (
    <header className="bg-background/90 z-20 border-b backdrop-blur sm:sticky sm:top-0">
      {data?.sample_mode && (
        <div className="bg-accent text-accent-foreground px-4 py-1 text-center text-xs">
          試しのデータで表示しています（デザイン確認用。記事の内容は架空です）
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
        <div className="flex min-w-full flex-wrap items-center gap-x-3 gap-y-1 text-sm sm:min-w-0 sm:flex-1">
          {run ? (
            <>
              <span className="inline-flex items-center gap-1.5 font-medium">
                <Icon
                  className={cn('size-4', STATUS_ICON[run.status].className)}
                  aria-hidden="true"
                />
                {running ? '更新中…' : `前回の更新：${RUN_STATUS_LABEL[run.status]}`}
              </span>
              {!running && (
                <span className="text-muted-foreground">
                  {formatDateTime(run.started_at)}　新着 {run.new_count}件・選定{' '}
                  {run.selected_count}件
                </span>
              )}
              {run.issues.length > 0 && !running && (
                <span className="text-muted-foreground">問題 {run.issues.length}件</span>
              )}
              {run.previous_model_id && run.previous_model_id !== run.model_id && !running && (
                <span className="bg-accent text-accent-foreground rounded px-1.5 py-0.5 text-xs">
                  モデル変更：{run.previous_model_id} → {run.model_id}
                </span>
              )}
            </>
          ) : (
            <span className="text-muted-foreground">まだ更新していません</span>
          )}
          {start.isError && (
            <span role="alert" className="text-destructive">
              更新を始められませんでした：
              {start.error instanceof ApiError && start.error.detail
                ? start.error.detail
                : '時間をおいてもう一度お試しください'}
            </span>
          )}
        </div>

        {budget && (
          <div className="text-muted-foreground flex items-center gap-2 text-xs">
            <span className="whitespace-nowrap">
              今月 {formatUsd(budget.month_cost_usd)} / {formatUsd(budget.month_limit_usd)}
            </span>
            <div
              role="meter"
              aria-label="今月の費用"
              aria-valuemin={0}
              aria-valuemax={budget.month_limit_usd}
              aria-valuenow={budget.month_cost_usd}
              className="bg-border h-1.5 w-20 overflow-hidden rounded-full"
            >
              <div
                className={cn(
                  'h-full rounded-full',
                  ratio >= 0.8 ? 'bg-status-warning' : 'bg-primary',
                )}
                style={{ width: `${ratio * 100}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Button
            type="button"
            size="sm"
            disabled={running || start.isPending}
            onClick={() => start.mutate()}
          >
            <RefreshCw className={cn('size-4', running && 'animate-spin')} aria-hidden="true" />
            更新
          </Button>
        </div>
      </div>
    </header>
  )
}
