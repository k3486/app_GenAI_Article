/** バックエンド API 呼び出しの共通処理。API はすべてこの関数経由で呼ぶ。 */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) {
    throw new ApiError(response.status, `GET /api${path} failed: ${response.status}`)
  }
  return (await response.json()) as T
}
