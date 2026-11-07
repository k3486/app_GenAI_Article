# タスク

## 1. 準備
- [x] プロジェクト名を `ai-news-dashboard` に決定し、`scripts/init_project.sh` を実行（2026-11-07）
- [x] ideas の案を「採用」に更新
- [x] `.steering/20261107-local-dashboard/` に requirements / design / tasklist を作成
- [ ] `.env.example` に `ANTHROPIC_API_KEY=`（Haiku 用）を追記 ※権限設定で私は読み書きできない。上司が追記する（`BRAVE_API_KEY` は既に載っている報告）。本物のキーは `../.secrets/.env` に上司が入れ、その後コンテナの再起動が必要。G2 の前までに
- [x] 初期化後の確認: `make setup && make lint && make test`（lint・型チェック・テストすべて通過。backend 9件・frontend 1件）
- [x] 興味プロファイルの叩き台を上司が承認 → `backend/config/interest_profile.default.md`（初期値。アプリ起動時に DB へ登録し、以降は画面から直す）
- [ ] Playwright 用ブラウザの導入（収集の段階で必要になった時点でよい）

## 2. 画面だけ先に作る（試しのデータ）→ G1
- [x] API の形（契約）を決める（`backend/app/schemas/`。`make types` で OpenAPI から `frontend/src/lib/api-types.ts` を生成）
- [x] 試しのデータを返す API（`backend/app/services/sample_store.py`。**段階3で本物に置き換えて削除する**）。点数の計算・選定の判定は本物のコード（`services/scoring.py`）
- [x] 画面の部品を追加（React Router・TanStack Query・TanStack Table 9・Recharts。shadcn の部品も追加）
- [x] 7シートの実装（最新トピック／お気に入り／バックログ／全記事／落選記事／分析／設定・運用）。ライト・ダーク両対応、スマホ幅も確認済み
- [x] 検証: `make lint && make test` 通過（backend 30件・frontend 7件）。バックエンドは実サーバーに HTTP で当てる E2E 37項目すべて成功。画面は Playwright で、PC（ライト・ダーク）・スマホ幅・更新ボタンを確認
- [ ] **G1: 上司にデザインを確認してもらう**（確認待ち）
- 未実装（G5 で作る）: 壁打ち、好みメモ、プロファイルの修正案（ホームのバッジ・設定の承認カード）

## 3. DB と API → 4. 収集 → G2
- [x] G1 承認（2026-11-07 上司「フロントは良い感じです」）
- [x] 3. DB と API: SQLModel の表（11表）、Alembic（`0001`。モデルとのずれはテストで検知）、SQLite の WAL・外部キー・待ち時間、全文検索（FTS5・trigram）、バックアップ（7世代）、services（topics／insights／runs／sources／app_settings／search／backup）。試しのデータは `make seed`（`scripts/seed_sample.py`）に移した。`POST /api/runs` は段階6まで 501
- [x] 検証: `make lint && make test` 通過（backend 49件・frontend 8件）。本物の DB につないだ実サーバーへの E2E 37項目すべて成功。9p のフォルダでの3プロセス同時書き込み試験でエラー0・整合性OK
- 追記済みで未対応: `backend/CLAUDE.md` の「Alembic は未導入」の記述が古い（上司の了承を得て直す）
- [x] 4. 収集のコード（2026-11-07）: `config/sources.yaml`（29件・使えるのは26件。RSS／サイトマップ／一覧／Zenn／Qiita／HF を実際に取得して確認済み）、`config/scoring.yaml`（AI 関連語）、`app/services/collect/`（urls・fetcher・extract・browser・collectors・pipeline・run・source_config）、`scripts/collect.py`、移行 `0002`（記事に summary・fetch_error）。テスト backend 178件・lint・型チェック通過
- [x] 4. 収集の実地確認（2026-11-07 実施。試しのデータは消去済み・バックアップ有）: 候補3,366→通過186→全文172・概要のみ10（OpenAI News 全件 HTTP 403）・失敗2・対象外2。ブラウザ取り直しは0回（未検証のまま）。結果は G2 で報告
- [x] G2 の事後作業（2026-11-07）: 候補の上限の既定を 80→200（`app_settings.py`・DB の保存値も更新）、`make collect` を追加、`docs/` に収集の仕様を反映、`backend/CLAUDE.md` の Alembic 記述を修正。`make lint`・pytest 178件・Vitest 8件 通過
- [ ] **G2: 本文の取得率と取れなかったサイトを確認（Haiku を使う前）** ※資料は決定事項に記載済み。上司の最終了承待ち
- [ ] `ANTHROPIC_API_KEY` がコンテナに届かない件の原因調査（env-file はコンテナ作成時のみ読込。Rebuild 未実施／書式／変数名の疑い。上司の端末での確認待ち）

## 5. Haiku の処理 → G3 → G4
- [ ] LLM の口（最新 Haiku の選択・費用の記録・上限）、スキルの読み込み
- [ ] 採点・話題の判定・検索語の生成 → **G3**
- [ ] 整理記事（5種類） → **G4**

## 6〜8. 更新ボタン・壁打ち・フィードバック → G5
- [ ] 更新ボタン（別プロセス・非同期の並列処理・実行履歴）
- [ ] 壁打ち、好みメモ、プロファイルの修正案 → **G5**
- [ ] 試しのデータを消し、本物の記事で確認。点数のぶれの検査
- [ ] `docs/spec.md`・`docs/architecture.md` の更新、`history.md` に追記

## 次にやること
1. **本番の収集を1回実行して、G2 の資料を作る**: `cd backend && uv run python -m scripts.collect --max-candidates 200`（約1〜3分。DB に書く）。出力の「本文の取得結果（情報源ごと）」を表にして上司に見せる（全文／概要のみ／失敗・平均文字数・失敗の理由）。取れなかったサイトの原因（robots・JS 描画・有料・タイムアウト）を分類する。実行前に、試しのデータをどうするか決める（`make`の seed が入っている。本物の記事と混ぜないなら `uv run python -m scripts.seed_sample --clear`）
2. ブラウザでの取り直し（Playwright＋`/usr/bin/google-chrome`）は、実サイトでは**未確認**。1 の実行で `ブラウザで取り直し N` が出るか見る。起動できなければ `browser_unavailable` と出る
3. 1 の結果で、`config/sources.yaml` を直す（取れないサイトは `disabled_reason` を付ける）
4. **G2: 上司に確認**: 本文の取得率・取れなかったサイト。あわせて次の判断を仰ぐ → ①候補の最大件数の既定（下の発見を参照）、②Brave Search の扱い（下記）
5. G2 通過後は「5. Haiku の処理」へ。その前に `docs/spec.md`・`docs/architecture.md` に収集の仕様を反映し、`Makefile` に `collect` の目標を足す（未実施）

## 決定事項（2026-11-07 G2 の議論）
- OpenAI News は Cloudflare の確認画面で、ブラウザでも本文を取れない（HTTP 403／確認画面）。防御を破る細工はしない。**対応: 同じ話題を扱う他媒体（TechCrunch・The Verge・ITmedia など）の本文を、④話題のまとめ→⑥採点の材料に使う**。取れない公式記事は画面に「全文未取得」と表示。実装は段階5（話題のまとめ）で行う
- ブラウザでの取り直しは実サイトで起動を確認済み（Chrome 起動 OK）。通常の取得で本文が短いページ用として維持する
- **Brave Search は使わない（案A確定）**。原文の規約 §3(b)(i) が検索結果の保存・DB 化を禁止（非商用の例外なし）、§3(b)(xiii) が AI の評価・改善への利用を禁止。`queries` スキルは作らない。収集は RSS・サイトマップ・一覧・Zenn・Qiita・HF のみ
- 未回答: 候補の上限の既定を 80→200 に上げる件（推奨のまま進めてよいか確認）

## 中断メモ（どこまで進んだか・気になっている点）
- 2026-11-07: G1 承認 → 段階3（DB と API）完了 → 段階4（収集）のコードとテストまで完了。**実地の収集（DB に書く本番実行）はまだ1回もしていない**。DB（`data/app.db`）には移行 0002 まで適用済み＋試しのデータ（`make seed`）が入っている。
- **試し実行（`--dry-run`、実サイト）の結果**: 26情報源から候補 3,356件 → 通過 80件（約21秒）。直近3日の新しい候補は約162件あり、**上限80件で約半分が切られ、公式が優先されるためメディア（ITmedia 17件・The Batch 20件・TechCrunch 13件など）が大きく落ちる**。→ G2 で「候補の上限の既定を上げる（例 160〜200）」を提案する。Haiku の費用は採点50件の上限が守る（候補の上限は通信時間だけの話）。
- 試し実行で見つけて**直した不具合**: ①Qiita が1回の応答 5MB 超で失敗 → 期間指定（`created:>=日付`）＋1回50件に変更（テスト済み）。②英語の短い見出しを外国語と誤判定 → 短い文は「判定できない」で通す（300字以上のときだけ「その他」）。③HF Daily Papers が全部「古い」になる → 日次リストの日付で見るように変更。④中国語を日本語と誤判定 → 仮名を目印にする。⑤想定外のデータの形を拾えない → 例外を拡大。⑥日本語記事の「本文が短い」の基準が厳しすぎる → 日本語は 200 字（英語は 400 字）。
- **Brave Search は組み込んでいない（保留）**: 無料プランは 2026年2月に廃止（毎月 $5 分のクレジットの従量課金。カード登録が必要。1日5検索なら月約 $0.75）。規約（公式ページを要約ツールで読んだ内容。要確認）に「検索結果を DB に保存してはいけない」「検索結果を AI の評価・改善に使ってはいけない」という趣旨の条項があり、この計画（検索結果から記事を集めて DB に保存し Haiku で採点）と衝突する可能性がある。上司に、①Brave をやめる（RSS・サイトマップ・Zenn・Qiita・HF だけで運用）②規約を確認したうえで使う、を選んでもらう。`queries` スキル（検索語の生成）も、この結論まで作らない。
- arXiv は規約で「3秒に1回・同時接続1つ」。`sources.yaml` と `Fetcher` に反映済み（テスト済み）。
- 使えない情報源（`disabled_reason` あり）: Anthropic Engineering・Claude Blog（一覧が JS 描画でサイトマップにも無い。ブラウザでの一覧取得が必要）、VentureBeat（429）。
- 気づき: ①このリポジトリは 9p のフォルダで、ファイルの変更が通知されない（`vite.config.ts` にポーリングを足して解決済み）。②`pkill -f` では親の make が残る。PID を指定して止める。③`trafilatura` は同じ段落の繰り返しを取り除くので、テスト用 HTML の段落は重複させない（`tests/helpers.py` で対応済み）。④HTTP クライアントは `httpx2`（モジュール名も `httpx2`）。
- 上司への確認待ち（前から）: `backend/CLAUDE.md` の「Alembic は未導入」の記述が古い（直してよいか）／`.env.example` に `ANTHROPIC_API_KEY=` を足す（上司が実施。`../.secrets/.env` に本物のキー＋コンテナの再起動。G2 の後・Haiku を使う前に必要）。
- 未コミット（コミットは指示があるときだけ）。開発サーバーは停止済み（`make dev` で起動）。
- 開発サーバーを止めるときは、プロセスを PID で指定して止める（`pkill -f` のパターンでは親の make が残ることがあった）。
