import { Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ARTICLE_TYPE_LABEL, CATEGORY_LABEL } from '@/lib/labels'
import { useSources } from '@/lib/queries'
import type { ArticleType, Category } from '@/lib/types'

export type Filters = {
  q: string
  type?: ArticleType
  category?: Category
  source?: string
}

const ALL = '__all__'

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string | undefined
  onChange: (value: string | undefined) => void
  options: { value: string; label: string }[]
}) {
  return (
    <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
      <SelectTrigger aria-label={label} className="w-full min-w-0 sm:w-auto sm:min-w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{label}：すべて</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** 検索語・種類・トピック・情報源での絞り込み。 */
export function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters
  onChange: (next: Filters) => void
}) {
  const sources = useSources()
  // 入力中は手元の値を使い、少し待ってから一覧を取り直す
  const [text, setText] = useState(filters.q)
  useEffect(() => {
    if (text === filters.q) return
    const timer = setTimeout(() => onChange({ ...filters, q: text }), 250)
    return () => clearTimeout(timer)
  }, [text, filters, onChange])

  const active = Boolean(filters.q || filters.type || filters.category || filters.source)

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <div className="relative sm:w-64">
        <Search
          className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
          aria-hidden="true"
        />
        <Input
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="タイトル・要約・タグで検索"
          aria-label="検索"
          className="pl-9"
        />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:flex">
        <FilterSelect
          label="種類"
          value={filters.type}
          onChange={(v) => onChange({ ...filters, type: v as ArticleType | undefined })}
          options={Object.entries(ARTICLE_TYPE_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <FilterSelect
          label="トピック"
          value={filters.category}
          onChange={(v) => onChange({ ...filters, category: v as Category | undefined })}
          options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))}
        />
        <FilterSelect
          label="情報源"
          value={filters.source}
          onChange={(v) => onChange({ ...filters, source: v })}
          options={(sources.data ?? []).map((s) => ({ value: s.name, label: s.name }))}
        />
      </div>
      {active && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setText('')
            onChange({ q: '' })
          }}
        >
          <X className="size-4" aria-hidden="true" />
          条件をクリア
        </Button>
      )}
    </div>
  )
}
