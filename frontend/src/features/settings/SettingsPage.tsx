import { CircleAlert, CircleCheck, CircleX, TriangleAlert } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { ErrorNotice, PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { formatDateTime, formatUsd } from '@/lib/format'
import { PreferenceTab } from '@/features/settings/PreferenceTab'
import { ProfileVersions } from '@/features/settings/ProfileVersions'
import { ProposalCards } from '@/features/settings/ProposalCards'
import { RUN_STATUS_LABEL, SOURCE_KIND_LABEL } from '@/lib/labels'
import { useRuns, useSaveSettings, useSettings, useSources, useToggleSource } from '@/lib/queries'
import type { RunStatus, Settings } from '@/lib/types'
import { cn } from '@/lib/utils'

const WEIGHT_LABELS: [keyof Settings['weights'], string][] = [
  ['interest', '関心との一致'],
  ['practical', '実用性（論文・発表は「実務・事業への示唆」）'],
  ['freshness', '新しさ・重要度'],
  ['trust', '信頼性'],
  ['depth', '内容の深さ'],
]

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-muted-foreground block text-xs">{hint}</span>}
    </label>
  )
}

function NumberField({
  label,
  hint,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string
  hint?: string
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
}) {
  return (
    <Field label={label} hint={hint}>
      <Input
        type="number"
        inputMode="decimal"
        value={Number.isNaN(value) ? '' : value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.valueAsNumber)}
        className="w-32 tabular-nums"
      />
    </Field>
  )
}

const RUN_ICON: Record<RunStatus, typeof CircleCheck> = {
  running: CircleCheck,
  succeeded: CircleCheck,
  partial: TriangleAlert,
  budget_stopped: CircleAlert,
  failed: CircleX,
}
const RUN_COLOR: Record<RunStatus, string> = {
  running: 'text-primary',
  succeeded: 'text-status-good',
  partial: 'text-status-warning',
  budget_stopped: 'text-status-warning',
  failed: 'text-status-critical',
}

function SourcesTab() {
  const { data, isPending, isError } = useSources()
  const toggle = useToggleSource()
  if (isError) return <ErrorNotice />
  if (isPending) return <Skeleton className="h-48 rounded-xl" />
  return (
    <div className="bg-card overflow-x-auto rounded-xl border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground border-b text-left text-xs">
          <tr>
            <th scope="col" className="px-3 py-2.5 font-medium">
              情報源
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              種別
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              候補
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              選定
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              👍
            </th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">
              平均点
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              使う
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((s) => (
            <tr key={s.key} className="border-b last:border-0">
              <td className="px-3 py-2.5 font-medium">{s.name}</td>
              <td className="px-3 py-2.5">
                <Badge variant="outline">{SOURCE_KIND_LABEL[s.kind]}</Badge>
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">{s.candidates}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{s.selected}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">{s.likes}</td>
              <td className="px-3 py-2.5 text-right tabular-nums">
                {s.avg_score === null ? '—' : s.avg_score.toFixed(1)}
              </td>
              <td className="px-3 py-2.5">
                <Switch
                  checked={s.enabled}
                  aria-label={`${s.name} を使う`}
                  onCheckedChange={(enabled) => toggle.mutate({ key: s.key, enabled })}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-muted-foreground border-t px-3 py-2 text-xs">
        情報源の追加・削除は設定ファイル（sources.yaml）で行います。ここでは使う／使わないを切り替えます。
      </p>
    </div>
  )
}

function RunsTab() {
  const { data, isPending, isError } = useRuns()
  if (isError) return <ErrorNotice />
  if (isPending) return <Skeleton className="h-48 rounded-xl" />
  return (
    <ul className="space-y-3">
      {data.map((run) => {
        const Icon = RUN_ICON[run.status]
        return (
          <li key={run.id} className="bg-card rounded-xl border p-4">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="inline-flex items-center gap-1.5 font-medium">
                <Icon className={cn('size-4', RUN_COLOR[run.status])} aria-hidden="true" />
                {RUN_STATUS_LABEL[run.status]}
              </span>
              <span className="text-muted-foreground">
                {formatDateTime(run.started_at)}（{run.trigger === 'manual' ? '手動' : '定時'}）
              </span>
              <span className="tabular-nums">
                新着 {run.new_count}・採点 {run.scored_count}・選定 {run.selected_count}
              </span>
              <span className="tabular-nums">{formatUsd(run.cost_usd)}</span>
              <span className="text-muted-foreground text-xs">{run.model_id}</span>
            </div>
            {run.issues.length > 0 && (
              <ul className="mt-2 space-y-1 text-sm">
                {run.issues.map((issue, i) => (
                  <li key={i} className="text-muted-foreground flex gap-2">
                    <TriangleAlert
                      className="text-status-warning mt-0.5 size-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span>
                      <span className="text-foreground font-medium">{issue.source_name}</span>（
                      {issue.stage}）{issue.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {run.search_queries.length > 0 && (
              <details className="mt-2 text-sm">
                <summary className="text-muted-foreground cursor-pointer">
                  Haiku が作った検索語（{run.search_queries.length}）
                </summary>
                <ul className="mt-1.5 space-y-0.5 pl-4">
                  {run.search_queries.map((q) => (
                    <li key={q.query} className="flex gap-2">
                      <Badge variant="outline" className="text-xs">
                        {q.language === 'ja' ? '日本語' : '英語'}
                      </Badge>
                      <span>{q.query}</span>
                      <span className="text-muted-foreground text-xs">{q.result_count}件</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function ProfileTab({
  value,
  onChange,
  dirty,
}: {
  value: Settings
  onChange: (next: Settings) => void
  dirty: boolean
}) {
  return (
    <div className="space-y-2">
      <Field
        label="興味プロファイル"
        hint="採点のたびに Haiku が読む「あなたの好みの説明書」です。具体的に書くほど、判定がぶれません。変更は、次の更新から集める記事に反映されます（過去の記事は再採点しません）。"
      >
        <Textarea
          value={value.profile}
          onChange={(e) => onChange({ ...value, profile: e.target.value })}
          rows={16}
          className="leading-relaxed"
        />
      </Field>
      <p className="text-muted-foreground text-xs tabular-nums">{value.profile.length} 文字</p>
      <ProfileVersions locked={dirty} />
    </div>
  )
}

function ScoringTab({ value, onChange }: { value: Settings; onChange: (next: Settings) => void }) {
  const sum = Object.values(value.weights).reduce((a, b) => a + b, 0)
  return (
    <div className="space-y-8">
      <section>
        <h3 className="mb-1 text-base font-semibold">観点の重み</h3>
        <p className="text-muted-foreground mb-3 text-sm">
          5つの観点の重みです。合計は 100
          にしてください。重みを変えても、保存済みの点数から計算し直せます（Haiku は呼びません）。
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {WEIGHT_LABELS.map(([key, label]) => (
            <NumberField
              key={key}
              label={label}
              value={value.weights[key]}
              min={0}
              max={100}
              onChange={(n) => onChange({ ...value, weights: { ...value.weights, [key]: n } })}
            />
          ))}
        </div>
        <p
          className={cn(
            'mt-3 text-sm tabular-nums',
            sum === 100 ? 'text-muted-foreground' : 'text-destructive font-medium',
          )}
          role={sum === 100 ? undefined : 'alert'}
        >
          合計 {sum}
          {sum === 100 ? '' : '（100 にしてください）'}
        </p>
      </section>
      <section>
        <h3 className="mb-3 text-base font-semibold">選定と件数</h3>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <NumberField
            label="選定のしきい値（点）"
            hint="この点数以上を選定します（関心が2以下は除く）"
            value={value.threshold}
            min={0}
            max={110}
            onChange={(n) => onChange({ ...value, threshold: n })}
          />
          <NumberField
            label="1回に選ぶ最大件数"
            value={value.max_selected}
            min={1}
            max={50}
            onChange={(n) => onChange({ ...value, max_selected: n })}
          />
          <NumberField
            label="重大ニュースの最大件数"
            value={value.max_major}
            min={0}
            max={10}
            onChange={(n) => onChange({ ...value, max_major: n })}
          />
          <NumberField
            label="候補の最大件数"
            hint="本文を取りに行く前の打ち切り"
            value={value.max_candidates}
            min={1}
            max={300}
            onChange={(n) => onChange({ ...value, max_candidates: n })}
          />
          <NumberField
            label="採点の最大件数"
            hint="話題をまとめた後の代表記事の数"
            value={value.max_scored}
            min={1}
            max={200}
            onChange={(n) => onChange({ ...value, max_scored: n })}
          />
        </div>
      </section>
    </div>
  )
}

function BudgetTab({ value, onChange }: { value: Settings; onChange: (next: Settings) => void }) {
  return (
    <section>
      <h3 className="mb-1 text-base font-semibold">Haiku の費用の上限</h3>
      <p className="text-muted-foreground mb-3 text-sm">
        超えると処理を止め、残りは次回に回します。使った額は画面の上部に表示されます。
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <NumberField
          label="月の上限（ドル）"
          value={value.month_limit_usd}
          min={0.5}
          max={1000}
          step={0.5}
          onChange={(n) => onChange({ ...value, month_limit_usd: n })}
        />
        <NumberField
          label="1回の更新の上限（ドル）"
          hint="不具合で同じ記事を何度も処理してしまう事故を防ぎます"
          value={value.run_limit_usd}
          min={0.05}
          max={100}
          step={0.05}
          onChange={(n) => onChange({ ...value, run_limit_usd: n })}
        />
      </div>
    </section>
  )
}

function isValid(s: Settings): boolean {
  const sum = Object.values(s.weights).reduce((a, b) => a + b, 0)
  const numbers = [
    ...Object.values(s.weights),
    s.threshold,
    s.max_selected,
    s.max_major,
    s.max_candidates,
    s.max_scored,
    s.month_limit_usd,
    s.run_limit_usd,
  ]
  return (
    sum === 100 &&
    numbers.every((n) => Number.isFinite(n)) &&
    s.max_selected >= 1 &&
    s.profile.trim() !== ''
  )
}

export function SettingsPage() {
  const { data, isPending, isError } = useSettings()
  const save = useSaveSettings()
  const [draft, setDraft] = useState<Settings | null>(null)
  const value = draft ?? data
  const dirty = draft !== null

  return (
    <>
      <PageHeader
        title="設定・運用"
        description="好み・採点・費用の設定と、情報源、更新の実行履歴です。"
      />
      {isError && <ErrorNotice />}
      {isPending && <Skeleton className="h-96 rounded-xl" />}
      <ProposalCards locked={dirty} />
      {value && (
        <Tabs defaultValue="profile">
          <TabsList className="mb-4 h-auto flex-wrap justify-start">
            <TabsTrigger value="profile">興味プロファイル</TabsTrigger>
            <TabsTrigger value="preference">好みメモ</TabsTrigger>
            <TabsTrigger value="scoring">採点と選定</TabsTrigger>
            <TabsTrigger value="budget">費用と上限</TabsTrigger>
            <TabsTrigger value="sources">情報源</TabsTrigger>
            <TabsTrigger value="runs">実行履歴</TabsTrigger>
          </TabsList>

          <TabsContent value="profile">
            <ProfileTab value={value} onChange={setDraft} dirty={dirty} />
          </TabsContent>
          <TabsContent value="preference">
            <PreferenceTab />
          </TabsContent>
          <TabsContent value="scoring">
            <ScoringTab value={value} onChange={setDraft} />
          </TabsContent>
          <TabsContent value="budget">
            <BudgetTab value={value} onChange={setDraft} />
          </TabsContent>
          <TabsContent value="sources">
            <SourcesTab />
          </TabsContent>
          <TabsContent value="runs">
            <RunsTab />
          </TabsContent>

          <div className="bg-card/95 sticky bottom-20 mt-6 flex flex-wrap items-center gap-3 rounded-xl border p-3 shadow-md backdrop-blur lg:bottom-4">
            <span className="text-muted-foreground flex-1 text-sm" aria-live="polite">
              {save.isError
                ? '保存できませんでした。入力を確認してください。'
                : save.isSuccess && !dirty
                  ? '保存しました。次の更新から反映されます。'
                  : dirty
                    ? '未保存の変更があります'
                    : '変更はありません'}
            </span>
            <Button type="button" variant="ghost" disabled={!dirty} onClick={() => setDraft(null)}>
              変更を破棄
            </Button>
            <Button
              type="button"
              disabled={!dirty || !isValid(value) || save.isPending}
              onClick={() => save.mutate(value, { onSuccess: () => setDraft(null) })}
            >
              保存
            </Button>
          </div>
        </Tabs>
      )}
    </>
  )
}
