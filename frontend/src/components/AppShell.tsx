import {
  Archive,
  ChartColumn,
  Inbox,
  Newspaper,
  Settings,
  Star,
  Table2,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { StatusBar } from '@/components/StatusBar'
import { TopicDetailDialog } from '@/components/TopicDetailDialog'
import { useTopics } from '@/lib/queries'
import { cn } from '@/lib/utils'

type NavItem = { to: string; label: string; short: string; icon: LucideIcon }

const NAV: NavItem[] = [
  { to: '/', label: '最新トピック', short: '最新', icon: Newspaper },
  { to: '/favorites', label: 'お気に入り記事', short: 'お気に入り', icon: Star },
  { to: '/backlog', label: 'バックログ', short: '未読', icon: Inbox },
  { to: '/articles', label: '全記事', short: '全記事', icon: Table2 },
  { to: '/rejected', label: '落選記事', short: '落選', icon: Archive },
  { to: '/insights', label: '分析', short: '分析', icon: ChartColumn },
  { to: '/settings', label: '設定・運用', short: '設定', icon: Settings },
]

function BacklogCount() {
  const { data } = useTopics({ view: 'backlog', pageSize: 1 })
  if (!data || data.total === 0) return null
  return (
    <span
      className="bg-primary text-primary-foreground ml-auto rounded-full px-1.5 text-xs font-medium tabular-nums"
      aria-label={`未読 ${data.total}件`}
    >
      {data.total}
    </span>
  )
}

/** 左のナビ（PC）／下のタブ（スマホ）＋上部の状態バー＋記事の詳細。 */
export function AppShell() {
  return (
    <div className="min-h-svh lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="bg-sidebar hidden border-r lg:block">
        <div className="sticky top-0 flex h-svh flex-col gap-1 p-4">
          <div className="mb-4 px-2 pt-1">
            <p className="text-base leading-tight font-semibold">AI ニュース</p>
            <p className="text-muted-foreground text-xs">ダッシュボード</p>
          </div>
          <nav aria-label="シート" className="flex flex-col gap-0.5">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  cn(
                    'hover:bg-sidebar-accent flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive && 'bg-sidebar-accent text-sidebar-accent-foreground font-semibold',
                  )
                }
              >
                <Icon className="size-4" aria-hidden="true" />
                {label}
                {to === '/backlog' && <BacklogCount />}
              </NavLink>
            ))}
          </nav>
        </div>
      </aside>

      <div className="flex min-w-0 flex-col pb-20 lg:pb-0">
        <StatusBar />
        <main className="flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>

      <nav
        aria-label="シート"
        className="bg-sidebar fixed inset-x-0 bottom-0 z-30 grid grid-cols-7 border-t pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {NAV.map(({ to, short, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'text-muted-foreground flex flex-col items-center gap-0.5 px-0.5 py-2 text-[10px]',
                isActive && 'text-primary font-semibold',
              )
            }
          >
            <Icon className="size-5" aria-hidden="true" />
            {short}
          </NavLink>
        ))}
      </nav>

      <TopicDetailDialog />
    </div>
  )
}
