import { QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/AppShell'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ArticlesPage } from '@/features/articles/ArticlesPage'
import { BacklogPage } from '@/features/backlog/BacklogPage'
import { FavoritesPage } from '@/features/favorites/FavoritesPage'
import { InsightsPage } from '@/features/insights/InsightsPage'
import { RejectedPage } from '@/features/rejected/RejectedPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { LatestPage } from '@/features/topics/LatestPage'
import { createQueryClient } from '@/lib/queryClient'

/** シートごとの画面。テストでは、これを MemoryRouter の中に置く。 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LatestPage />} />
        <Route path="favorites" element={<FavoritesPage />} />
        <Route path="backlog" element={<BacklogPage />} />
        <Route path="articles" element={<ArticlesPage />} />
        <Route path="rejected" element={<RejectedPage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  const [client] = useState(createQueryClient)
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={300}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
