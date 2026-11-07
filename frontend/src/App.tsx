import { useEffect, useState } from 'react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { apiGet } from '@/lib/api'

type Health = { status: string; database: string }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    apiGet<Health>('/health', { signal: controller.signal })
      .then(setHealth)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(String(e))
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>app-template</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="text-destructive">API: {error}</p>}
          {!error && !health && <p className="text-muted-foreground">loading…</p>}
          {health && (
            <p>
              API: <span data-testid="health-status">{health.status}</span> / DB: {health.database}
            </p>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
