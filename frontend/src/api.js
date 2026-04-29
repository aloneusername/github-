const API_BASE = ''

export async function startAnalysis(repoUrl, force = false, model = '') {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl, force, model: model || null })
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function getProject(projectId) {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}`)
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export async function listProjects() {
  const response = await fetch(`${API_BASE}/api/projects`)
  if (!response.ok) throw new Error(await readError(response))
  return response.json()
}

export function subscribeAnalysis(projectId, onEvent) {
  const source = new EventSource(`${API_BASE}/api/analyze/${projectId}/events`)
  for (const type of ['queued', 'progress', 'completed', 'failed']) {
    source.addEventListener(type, (event) => onEvent(type, JSON.parse(event.data)))
  }
  source.onerror = () => source.close()
  return () => source.close()
}

export async function streamChat(projectId, question, model, onToken) {
  const response = await fetch(`${API_BASE}/api/projects/${projectId}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, model: model || null })
  })
  if (!response.ok) throw new Error(await readError(response))

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const event = parseSse(part)
      if (event.event === 'token') onToken(event.data.content)
    }
  }
}

function parseSse(raw) {
  const event = { event: 'message', data: {} }
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event.event = line.slice(6).trim()
    if (line.startsWith('data:')) event.data = JSON.parse(line.slice(5).trim())
  }
  return event
}

async function readError(response) {
  try {
    const data = await response.json()
    return data.detail || response.statusText
  } catch {
    return response.statusText
  }
}
