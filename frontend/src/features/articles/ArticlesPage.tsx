import { PageHeader } from '@/components/PageHeader'
import { TopicTable } from '@/components/TopicTable'

export function ArticlesPage() {
  return (
    <>
      <PageHeader
        title="全記事"
        description="これまでに選ばれた記事の一覧です。題名をクリックすると整理記事を開きます。"
      />
      <TopicTable variant="selected" />
    </>
  )
}
