import { PageHeader } from '@/components/PageHeader'
import { TopicTable } from '@/components/TopicTable'

export function RejectedPage() {
  return (
    <>
      <PageHeader
        title="落選記事"
        description="選ばれなかった記事です。読みたかった記事に「実はよかった」を付けると、次回からの採点に反映されます（整理記事は作りません）。"
      />
      <TopicTable variant="rejected" />
    </>
  )
}
