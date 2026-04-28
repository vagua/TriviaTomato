export interface QuizQuestion {
  prompt: string
  options: string[]
  answer_index: number
  explanation: string
}

const envBase = import.meta.env.VITE_BACKEND_URL?.trim()
const isBrowser = typeof window !== 'undefined'

const browserOrigin =
  isBrowser && window.location?.protocol && window.location?.hostname
    ? `${window.location.protocol}//${window.location.hostname}${
        window.location.port ? `:${window.location.port}` : ''
      }`
    : ''

const browserBackend =
  isBrowser && window.location?.protocol && window.location?.hostname
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : ''

const internalBackends = new Set(['backend', 'backend.default', 'backend.local'])

function resolveApiBase(): string {
  if (!envBase) {
    return browserBackend || ''
  }

  if (envBase.startsWith('/')) {
    return browserOrigin ? `${browserOrigin}${envBase}` : envBase
  }

  try {
    const parsed = new URL(envBase)
    if (internalBackends.has(parsed.hostname) && browserBackend) {
      return browserBackend
    }
    return parsed.origin + parsed.pathname.replace(/\/$/, '')
  } catch {
    return browserBackend || envBase
  }
}

const API_BASE = resolveApiBase()

async function handleResponse(response: Response) {
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || 'API request failed')
  }
  return response.json()
}

interface StartResponse {
  session_id: string
}

interface QuizResponse {
  questions: QuizQuestion[]
}

export async function startSession(activity: string): Promise<StartResponse> {
  const response = await fetch(`${API_BASE}/api/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ activity }),
  })
  return handleResponse(response)
}

export async function fetchQuiz(
  sessionId: string,
): Promise<QuizResponse> {
  const response = await fetch(`${API_BASE}/api/quiz/${sessionId}`)
  return handleResponse(response)
}
