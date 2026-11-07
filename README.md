# ai-news-dashboard

個人用 Web アプリの標準テンプレート。FastAPI（Python）＋ React（TypeScript）＋ SQLite。
Claude Code で開発する前提の設定（CLAUDE.md・スキル・MCP・hook）を含む。

| 層 | 技術 |
|---|---|
| backend | FastAPI, SQLModel(SQLite), pydantic-settings, uv, ruff, mypy, pytest |
| frontend | Vite, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, oxlint, Prettier, Vitest |
| 開発環境 | Dev Container（Python 3.12 / Node 26 / Claude Code） |


## フォルダの置き方（WSL）
```
<作業フォルダ>/            例: /workspaces/Project（WSL 内のパス。/mnt/c 配下は不可）
├── .secrets/.env          APIキー（全リポジトリ共通・git 管理外）
├── ai-news-dashboard/
└── <アプリ>/
```

## セットアップ
1. VS Code で**このリポジトリのフォルダ**を開き「Dev Containers: Reopen in Container」
   - 初回に `../.secrets/.env` が空で作られる。キーを書いたら **Rebuild Container**
   - 書式は `../.secrets/README.md`、必要なキーは `.env.example`
2. コンテナ作成時に `make setup` と Playwright 用の Chrome 導入が自動で走る
3. Claude Code は**このリポジトリ直下で起動**する（`.claude/` と `.mcp.json` はそこからしか読まれない）
4. 初回だけプラグインを入れる:
   ```
   claude plugin install frontend-design@claude-plugins-official --scope project
   ```
5. `claude mcp list` で MCP の接続を確認（brave-search・github はキー設定後）

## よく使うコマンド
```
make dev      # http://localhost:5173 （API は :8000）
make lint     # lint・整形・型チェック
make test     # pytest ＋ Vitest
make format   # 自動整形
```

## Claude Code の設定
| 種類 | 内容 |
|---|---|
| CLAUDE.md | 共通層 `~/.claude/CLAUDE.md`（役割・進め方・ドキュメント運用など全プロジェクト共通。`claude-code-config` ボリュームに保存され git 管理外）＋ ルート（このプロジェクト固有）・backend/・frontend/ |
| スキル | `grill-me`（同梱・MIT, Matt Pocock）、`frontend-design`（公式プラグイン）、skill-creator は claude.ai アカウントのものを使う |
| MCP | context7（ライブラリ文書）、playwright（画面確認）、brave-search（Web 検索）、github（リポジトリ・PR 操作）。aws-docs（AWS 文書）は定義だけ置いて止めている |
| コンテキスト節約 | コマンド出力は 10,000 文字を超えるとファイルに逃がす（`bashOutputMaxChars`）、使わない MCP は止める |
| hook | ファイル編集後に ruff format / prettier で自動整形（Python は ruff check も行い、違反を Claude に知らせる） |
| ステータスライン | `.claude/statusline.sh`。モデル·思考の深さ │ フォルダ ブランチ（`*` は未コミットあり） │ 会話の記憶の使用率 │ 5時間の利用上限の消費率 |
| 通知音 | 処理の終了・許可待ちでターミナルのベルを鳴らす（`preferredNotifChannel: "terminal_bell"`）。画面から離れているときに鳴る |
| モデル | `opusplan`（計画モードでは Opus、それ以外の作業では Sonnet。`/model` でいつでも切り替えられる） |
| 画面 | 返答は日本語（`language`）、時刻は日本時間の24時間表記（`timeZone`・`timeFormat`）、文章は100文字で折り返す（`maxProseWidth`）、Ctrl+O で考えの要約を表示（`showThinkingSummaries`） |
| 権限 | make・uv・npm 等を許可、`.env` の読み取りと `env`/`printenv` を拒否 |

GitHub MCP を使うには `../.secrets/.env` に `GITHUB_MCP_PAT` を書く（未設定だと github だけ接続失敗になる）。

通知音を鳴らすには、Windows 側の VS Code のユーザー設定で `"accessibility.signals.terminalBell": { "sound": "on" }` にする
（既定の auto では鳴らない。「リモート [Dev Container]」タブではなく「ユーザー」タブで設定する）。

> 注意: キーは環境変数としてコンテナに渡るため、Bash 経由での読み取りを完全には防げない。
> 権限の拒否設定は「うっかり表示」を防ぐためのもの。

## ドキュメント
| 場所 | 内容 |
|---|---|
| `docs/` | 現在の仕様（常に最新だけ） |
| `.steering/` | 作業履歴と中断・再開用のメモ |
| `ideas/` | 会話で出た実装案 |

## AWS に載せるとき（将来）
コードは環境変数から設定を読むだけなので変更不要。キーは SSM Parameter Store（SecureString）に置く。
AWS の文書を調べる aws-docs MCP は止めてあるので、作業を始めるときに `.claude/settings.json` の
`disabledMcpjsonServers` から `enabledMcpjsonServers` へ移す。
