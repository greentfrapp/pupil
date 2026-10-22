/** The server answered, but refused the request. */
export class RequestFailed extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

export async function failure(res: Response): Promise<RequestFailed> {
  const body = await res.json().catch(() => null)
  return new RequestFailed(body?.detail ?? `HTTP ${res.status}`, res.status)
}

export async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw await failure(res)
  return res.json()
}

export async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw await failure(res)
  return res.json()
}
