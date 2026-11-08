# 開発履歴（追記のみ）

| 日付 | 内容 | 記録 |
|---|---|---|
| 2026-11-07 | プロジェクトの土台（backend/frontend/docs/ideas/.steering・Dev Container）を作成 | Initial commit（`faf7eb7`） |
| 2026-11-07 | ローカルダッシュボードの実装: 画面7シート、DB(SQLModel/Alembic)とAPI、収集パイプライン（段階4まで）。G1・G2 の決定を記録 | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-07 | G2 の事後作業: 候補上限を80→200件、`make collect` 追加、docs に収集仕様を反映 | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-07 | G2 確定と API キーの疎通確認 | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-07 | 収集に Haiku の採点・グループ化・選定を追加／開発環境の高速化（SDK の import 約150秒→約1秒）／Vitest の不安定な失敗を解消 | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-07 | 話題のまとめの修正（Anthropic カテゴリページの除外、一覧ページの見出し取り直し、記事 ID の取り違え防止、判定の推論量を medium に）と DB のやり直し | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-07 | 告知・一覧ページの除外（exclude_titles）、OpenAI 公式は概要のみで登録（fetch_body: false）、概要だけの話題は重大ニュースにしない | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-07 | G3 通過。判定を reselect で最新化（選定 32→37・重大 3→1）、週刊ニュースレター（digest）は重大ニュースにしない | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-08 | G4 通過。整理記事（5種類・別の Haiku による校閲・「AI の意見」の区別）を実装。3行まとめは白背景＋黒枠 | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
| 2026-11-08 | G5 の実装: 更新ボタン（別プロセス・二重実行防止）、壁打ち（ツールを使う Haiku・メモ）、好みメモと興味プロファイルの修正案（承認・履歴・採点への反映）。実機で見つけた不具合3件を修正 | [.steering/20261107-local-dashboard/](20261107-local-dashboard/) |
