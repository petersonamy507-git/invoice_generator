/**
 * Invoice Finance API client.
 *
 * .env examples:
 *   VITE_API_BASE_URL=http://54.234.242.199:8082/api
 *   or leave empty and set VITE_API_PROXY_TARGET=http://54.234.242.199:8082
 *
 * Accepts base with or without trailing `/api` — request paths already start with `/api/...`.
 */
export function getApiBase(): string {
  const raw =
    (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
    (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ||
    ''
  return raw.replace(/\/+$/, '')
}

/** Join env base + path without doubling `/api`. */
export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path
  const base = API_BASE
  if (!base) return path
  if (/\/api$/i.test(base) && path.startsWith('/api')) {
    return `${base}${path.slice(4)}`
  }
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

const API_BASE = getApiBase()

type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  unauthorizedHandler = handler
}

export class ApiError extends Error {
  status: number
  detail: string
  body: unknown

  constructor(status: number, detail: string, body: unknown = null) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.body = body
  }
}

function messageFromBody(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback
  const data = body as Record<string, unknown>
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail) && data.detail[0] && typeof data.detail[0] === 'object') {
    const first = data.detail[0] as Record<string, unknown>
    if (typeof first.msg === 'string') return first.msg
  }
  if (typeof data.message === 'string') return data.message
  if (typeof data.error === 'string') return data.error
  return fallback
}

async function readErrorDetail(response: Response): Promise<{ detail: string; body: unknown }> {
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    const body = await response.json().catch(() => null)
    return { detail: messageFromBody(body, response.statusText || 'Request failed'), body }
  }
  const text = await response.text().catch(() => '')
  return { detail: text || response.statusText || 'Request failed', body: text || null }
}

/** Shared fetch helper — always sends invoice_session cookie. */
export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const url = apiUrl(path)
  let response: Response
  try {
    response = await fetch(url, {
      ...init,
      credentials: 'include',
      headers,
    })
  } catch {
    throw new ApiError(
      0,
      `Unable to reach API at ${API_BASE || window.location.origin}. Check VITE_API_BASE_URL and that the API host is up.`,
    )
  }

  if (response.status === 401) {
    const isLogin = path.includes('/api/auth/login')
    if (!isLogin) unauthorizedHandler?.()
    const { detail, body } = await readErrorDetail(response)
    throw new ApiError(401, isLogin ? detail || 'Unauthorized' : 'Session expired. Please sign in again.', body)
  }

  if (!response.ok) {
    const { detail, body } = await readErrorDetail(response)
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      throw new ApiError(
        response.status,
        `API gateway error (${response.status}). Is the backend running at ${API_BASE || 'the proxy target'}?`,
        body,
      )
    }
    throw new ApiError(response.status, detail, body)
  }

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }
  return (await response.blob()) as T
}

/** @deprecated Prefer `api()` — kept for existing imports */
export const apiRequest = api

export function unwrapList<T>(data: unknown, keys: string[] = ['items', 'data', 'results', 'employees', 'departments']): T[] {
  if (Array.isArray(data)) return data as T[]
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    for (const key of keys) {
      if (Array.isArray(record[key])) return record[key] as T[]
    }
  }
  return []
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
