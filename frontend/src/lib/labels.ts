/** API の値 → 画面に出す日本語。 */
import type {
  ArticleType,
  Category,
  DislikeReason,
  ReadState,
  RunStatus,
  Selection,
  SourceKind,
} from './types'

export const ARTICLE_TYPE_LABEL: Record<ArticleType, string> = {
  announcement: '発表・リリース',
  howto: '活用ノウハウ・事例',
  paper: '論文・研究',
  analysis: '解説・考察',
  industry: '業界動向・規制',
}

export const CATEGORY_LABEL: Record<Category, string> = {
  dev_tools_agents: '開発ツール・エージェント',
  models: '新モデル・性能比較',
  use_cases: '業務での活用事例',
  know_how: '活用ノウハウ',
  regulation_safety: '規制・安全性',
  industry_trends: '業界動向',
  other: 'その他',
}

/** グラフの並び順（カテゴリの固定の順序。色もこの順で割り当てる） */
export const CATEGORY_ORDER: Category[] = [
  'dev_tools_agents',
  'models',
  'use_cases',
  'know_how',
  'regulation_safety',
  'industry_trends',
  'other',
]

export const SOURCE_KIND_LABEL: Record<SourceKind, string> = {
  official: '公式',
  media: 'メディア',
  paper: '論文',
}

export const SELECTION_LABEL: Record<Selection, string> = {
  selected: '選定',
  major: '重大ニュース',
  rejected: '落選',
}

export const READ_STATE_LABEL: Record<ReadState, string> = {
  unread: '未読',
  read: '読了',
  dismissed: '見送り',
}

export const DISLIKE_REASON_LABEL: Record<DislikeReason, string> = {
  not_interested: '興味なし',
  already_known: 'もう知っていた',
  low_quality: '質が低い',
}

export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  running: '更新中',
  succeeded: '成功',
  partial: '一部失敗',
  budget_stopped: '上限で停止',
  failed: '失敗',
}
