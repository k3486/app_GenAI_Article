# frontend（Vite / React 19 / TypeScript / Tailwind v4 / shadcn/ui）

## 置き場の決まり（必要になったら作る）
| 場所 | 内容 |
|---|---|
| `src/App.tsx` | ルートの画面 |
| `src/features/<機能>/` | 機能単位（画面・部品・hooks・型をまとめる） |
| `src/components/ui/` | shadcn/ui の部品（**生成物。直接の大改造はしない**） |
| `src/components/` | 複数の機能で使う自作部品 |
| `src/lib/api.ts` | API 呼び出し。**fetch はここ経由**（`apiGet` 等） |
| `src/lib/utils.ts` | `cn()` など共通関数 |

import は `@/` エイリアスを使う（例: `@/components/ui/card`）。

## 規約
- スタイルは Tailwind のクラスで書く（CSS ファイルを増やさない）。テーマ変数は `src/index.css`
- UI 部品は shadcn から追加: `npx shadcn@latest add <name>`
- デザインを作るときは frontend-design スキルを使ってよい
- lint は oxlint ＋ Prettier（`npm run lint`）、型は `npm run typecheck`
- パッケージ追加は `npm install <pkg>`（lockfile もコミット）

## テスト
- Vitest ＋ Testing Library。テストは対象の隣に `*.test.tsx`
- fetch は `vi.stubGlobal('fetch', ...)` でモックする（`src/App.test.tsx` 参照）
- 実行: `npm test`（またはルートで `make test`）
- 画面の実際の動きは Playwright MCP で確認できる（`make dev` 起動中に http://localhost:5173）
