/** バックエンド API 呼び出しの共通処理。API はすべてこの関数経由で呼ぶ。 */
export class ApiError extends Error {
  readonly status: number
  /** サーバーが返した理由（画面に出せる日本語）。無ければ空 */
  readonly detail: string

  constructor(status: number, message: string, detail = '') {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function failure(method: string, path: string, response: Response): Promise<ApiError> {
  let detail = ''
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      detail = body.detail
    }
  } catch {
    // 本文が JSON でなければ、ステータスだけを伝える
  }
  return new ApiError(
    response.status,
    `${method} /api${path} failed: ${response.status}${detail ? ` ${detail}` : ''}`,
    detail,
  )
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) throw await failure('GET', path, response)
  return (await response.json()) as T
}

export async function apiSend<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    method,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw await failure(method, path, response)
  return (await response.json()) as T
}
