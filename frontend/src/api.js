// Thin fetch wrappers. Vite proxies /api to the backend on :8000.

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.status === 204 ? null : res.json()
}

const get = (p) => request(p)
const post = (p, body) => request(p, { method: 'POST', body: JSON.stringify(body ?? {}) })
const patch = (p, body) => request(p, { method: 'PATCH', body: JSON.stringify(body) })
const del = (p) => request(p, { method: 'DELETE' })

export const api = {
  meta: () => get('/meta'),
  overview: () => get('/overview'),
  latexStatus: () => get('/latex/status'),

  jobs: {
    list: () => get('/jobs'),
    create: (body) => post('/jobs', body),
    update: (id, body) => patch(`/jobs/${id}`, body),
    remove: (id) => del(`/jobs/${id}`),
    followup: (id, body) => post(`/jobs/${id}/followup`, body),
    addRound: (id, body) => post(`/jobs/${id}/rounds`, body),
    updateRound: (id, n, body) => patch(`/jobs/${id}/rounds/${n}`, body),
    addContact: (id, body) => post(`/jobs/${id}/contacts`, body),
    stats: () => get('/stats'),
    followupSuggestions: () => get('/followup-suggestions'),
  },

  resumes: {
    list: () => get('/resumes'),
    create: (body) => post('/resumes', body),
    update: (id, body) => patch(`/resumes/${id}`, body),
    remove: (id) => del(`/resumes/${id}`),
    stats: () => get('/resumes/stats'),
    setApplied: (id, index, applied) => patch(`/resumes/${id}/tailor/${index}`, { applied }),
    link: (id, jobId) => post(`/resumes/${id}/link/${jobId}`),
    // Streams the file through a blob so the browser keeps the server's
    // filename and a failure surfaces as a message rather than a broken tab.
    async download(id, format) {
      const res = await fetch(`/api/resumes/${id}/download?format=${format}`)
      if (!res.ok) {
        let detail = res.statusText
        try {
          detail = (await res.json()).detail ?? detail
        } catch {
          /* non-JSON error body */
        }
        throw new Error(detail)
      }
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      const url = URL.createObjectURL(await res.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = match?.[1] ?? `resume.${format}`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    },
  },

  dsa: {
    list: () => get('/dsa'),
    create: (body) => post('/dsa', body),
    update: (id, body) => patch(`/dsa/${id}`, body),
    remove: (id) => del(`/dsa/${id}`),
    stats: () => get('/dsa/stats'),
    revisionQueue: () => get('/dsa/revision-queue'),
    logIssue: (id, body) => post(`/dsa/${id}/issue`, body),
    logRevisit: (id, body) => post(`/dsa/${id}/revisit`, body),
  },

  design: {
    list: () => get('/design'),
    create: (body) => post('/design', body),
    update: (id, body) => patch(`/design/${id}`, body),
    remove: (id) => del(`/design/${id}`),
    stats: () => get('/design/stats'),
    revisionQueue: () => get('/design/revision-queue'),
    logIssue: (id, body) => post(`/design/${id}/issue`, body),
    logRevisit: (id, body) => post(`/design/${id}/revisit`, body),
    addArtifact: (id, body) => post(`/design/${id}/artifact`, body),
  },

  chat: {
    health: () => get('/chat/health'),
    // Streams SSE; onEvent receives each decoded payload object.
    async send(message, sessionId, onEvent, signal) {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
        signal,
      })
      if (!res.ok || !res.body) throw new Error(`Chat failed: ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // SSE frames are separated by a blank line.
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          const line = frame.split('\n').find((l) => l.startsWith('data: '))
          if (!line) continue
          try {
            onEvent(JSON.parse(line.slice(6)))
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    },
  },
}
