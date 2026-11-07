import { BacklogTrendChart } from '@/components/charts/BacklogTrendChart'
import { CategoryBarChart } from '@/components/charts/CategoryBarChart'
import { CategoryTrendChart } from '@/components/charts/CategoryTrendChart'
import { EffectivenessPanel } from '@/components/charts/ScoreLikeChart'
import { SourceStatsTable } from '@/components/charts/SourceStatsTable'
import { ErrorNotice, PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/ui/skeleton'
import { useInsights } from '@/lib/queries'

export function InsightsPage() {
  const { data, isPending, isError } = useInsights()

  return (
    <>
      <PageHeader
        title="分析"
        description="どんな話題が多いか、どの情報源が好みに合うか、採点が好みに合っているかを確かめます。"
      />
      {isError && <ErrorNotice />}
      {isPending && (
        <div className="grid gap-4 lg:grid-cols-2" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-80 rounded-xl" />
          ))}
        </div>
      )}
      {data && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <CategoryBarChart categories={data.categories} />
            <CategoryTrendChart trend={data.trend} />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <EffectivenessPanel effectiveness={data.effectiveness} />
            <BacklogTrendChart backlog={data.backlog} />
          </div>
          <SourceStatsTable sources={data.sources} />
        </div>
      )}
    </>
  )
}
