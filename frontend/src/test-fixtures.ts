import type { AppStatus, Insights, Settings, SourceInfo, TopicCard, TopicDetail } from '@/lib/types'

const now = new Date().toISOString()

export function makeCard(overrides: Partial<TopicCard> = {}): TopicCard {
  return {
    id: 1,
    title_ja: 'テスト用の記事タイトル',
    summary_1line: 'テスト用の1行要約です。',
    summary_5lines: ['1', '2', '3', '4', '5'],
    url: 'https://example.com/a',
    selection: 'selected',
    score: 84,
    breakdown: {
      criteria: [
        { key: 'interest', label: '関心との一致', score: 5, weight: 20 },
        { key: 'practical', label: '実用性（再現性・汎用性）', score: 5, weight: 25 },
        { key: 'freshness', label: '新しさ・重要度', score: 3, weight: 25 },
        { key: 'trust', label: '信頼性', score: 4, weight: 15 },
        { key: 'depth', label: '内容の深さ', score: 4, weight: 15 },
      ],
      official_bonus: 0,
      total: 84,
      reason: 'テストの理由',
    },
    article_type: 'howto',
    category: 'know_how',
    tags: ['テスト'],
    source_name: 'テスト情報源',
    source_kind: 'media',
    published_at: now,
    published_estimated: false,
    selected_at: now,
    run_id: 3,
    image_url: null,
    related_count: 0,
    rejection_reason: null,
    state: {
      read_state: 'unread',
      backlog: false,
      starred: false,
      rating: null,
      dislike_reason: null,
      missed: false,
    },
    ...overrides,
  }
}

export function makeDetail(overrides: Partial<TopicDetail> = {}): TopicDetail {
  return {
    ...makeCard(),
    digest: {
      lead: ['まとめ1', 'まとめ2', 'まとめ3'],
      sections: [
        {
          heading: '背景・課題',
          paragraphs: [{ text: '事実の段落です。', inference: false }],
        },
        {
          heading: '費用対効果',
          paragraphs: [{ text: '推測の段落です。', inference: true }],
        },
      ],
      model_id: 'claude-haiku-5-5',
      created_at: now,
    },
    notes: [],
    articles: [
      {
        title: 'テスト用の記事タイトル',
        url: 'https://example.com/a',
        source_name: 'テスト情報源',
        role: 'representative',
        published_at: now,
      },
    ],
    ...overrides,
  }
}

export const status: AppStatus = {
  latest_run: {
    id: 3,
    status: 'succeeded',
    trigger: 'manual',
    started_at: now,
    finished_at: now,
    new_count: 38,
    scored_count: 12,
    selected_count: 8,
    cost_usd: 0.13,
    model_id: 'claude-haiku-5-5',
    previous_model_id: 'claude-haiku-4-5',
    issues: [],
    search_queries: [],
  },
  budget: { month_cost_usd: 2.4, month_limit_usd: 10, run_limit_usd: 0.5 },
  pending_proposals: 0,
  sample_mode: true,
}

export const settings: Settings = {
  profile: '## 興味のあるテーマ\n- テスト',
  weights: { interest: 20, practical: 25, freshness: 25, trust: 15, depth: 15 },
  threshold: 60,
  max_selected: 10,
  max_major: 3,
  max_candidates: 80,
  max_scored: 50,
  month_limit_usd: 10,
  run_limit_usd: 0.5,
}

export const sources: SourceInfo[] = [
  {
    key: 'a',
    name: 'テスト情報源',
    kind: 'media',
    enabled: true,
    candidates: 3,
    selected: 2,
    likes: 1,
    avg_score: 70.5,
  },
]

export const insights: Insights = {
  categories: [{ category: 'know_how', count: 3 }],
  trend: [{ date: '2026-11-07', category: 'know_how', count: 3 }],
  backlog: [{ date: '2026-11-07', count: 5 }],
  sources: [
    {
      source_name: 'テスト情報源',
      kind: 'media',
      candidates: 3,
      selected: 2,
      likes: 1,
      dislikes: 0,
      avg_score: 70.5,
    },
  ],
  effectiveness: {
    selected_like_rate: 0.5,
    rejected_missed_rate: null,
    score_bins: [{ label: '60〜69点', topics: 1, like_rate: null }],
  },
}
