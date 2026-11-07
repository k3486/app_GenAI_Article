/** API の型（api-types.ts は `make types` で自動生成。ここから別名を付けて使う）。 */
import type { components } from './api-types'

type Schemas = components['schemas']

export type TopicCard = Schemas['TopicCard']
export type TopicDetail = Schemas['TopicDetail']
export type TopicList = Schemas['TopicList']
export type TopicState = Schemas['TopicState']
export type TopicStatePatch = Schemas['TopicStatePatch']
export type ScoreBreakdown = Schemas['ScoreBreakdown']
export type CriterionScore = Schemas['CriterionScore']
export type Digest = Schemas['Digest']
export type RelatedArticle = Schemas['RelatedArticle']
export type AppStatus = Schemas['AppStatus']
export type RunSummary = Schemas['RunSummary']
export type Insights = Schemas['Insights']
export type Settings = Schemas['Settings']
export type SourceInfo = Schemas['SourceInfo']

export type ArticleType = TopicCard['article_type']
export type Category = TopicCard['category']
export type SourceKind = TopicCard['source_kind']
export type Selection = TopicCard['selection']
export type ReadState = TopicState['read_state']
export type DislikeReason = NonNullable<TopicState['dislike_reason']>
export type RunStatus = RunSummary['status']
