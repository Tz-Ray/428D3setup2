export async function api(path, method = 'GET', body) {
  const response = await fetch('/api/' + path, {
    method,
    credentials: 'include',
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15000),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))).detail
    const message = Array.isArray(detail)
      ? detail.map((e) => e.msg).join(' · ')
      : detail
    throw new Error(message || 'Request failed (' + response.status + ')')
  }
  if (response.status !== 204) return response.json()
}
