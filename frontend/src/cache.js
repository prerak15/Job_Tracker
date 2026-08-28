/**
 * Session cache — one namespaced, versioned wrapper around sessionStorage.
 *
 * sessionStorage rather than localStorage, deliberately. "For this session"
 * means this browser tab: two tabs open on the tracker are two working
 * contexts, and a refresh in one must not adopt the other's open tab or its
 * snapshot. Closing the tab drops the lot, so resume text, contact details and
 * chat transcripts never outlive the window they were read in.
 *
 * Everything degrades to an in-memory Map when storage is unavailable (private
 * mode, storage disabled by policy): the page keeps working, it just forgets
 * on refresh. A cache is never allowed to be the reason the app breaks.
 */

import { useEffect, useState } from 'react'

const NAMESPACE = 'job-tracker:'

// Bump when a cached shape changes in a way an old entry can't satisfy. Old
// entries then become unreadable, so they are swept at load rather than left
// occupying the session's storage budget for the rest of the tab's life.
const CACHE_VERSION = 1
const PREFIX = `${NAMESPACE}v${CACHE_VERSION}:`

// Every key in one place — a typo'd string literal is a silently dead cache,
// which is the hardest kind of bug to notice because everything still works.
export const CACHE_KEYS = {
  tab: 'ui.tab',
  chatOpen: 'ui.chat-open',
  autoRefresh: 'ui.auto-refresh',
  dashboard: 'data.dashboard',
  dashboardAt: 'data.dashboard-at',
  chatMessages: 'chat.messages',
  chatSession: 'chat.session',
}

const memory = new Map()

// Probed once: touching sessionStorage at all throws in some privacy modes, and
// wrapping every call site in try/catch would bury the logic that matters.
const store = (() => {
  try {
    const probe = `${NAMESPACE}probe`
    window.sessionStorage.setItem(probe, '1')
    window.sessionStorage.removeItem(probe)
    return window.sessionStorage
  } catch {
    return null
  }
})()

// Object.keys snapshots the list, so removing while iterating is safe.
if (store) {
  for (const key of Object.keys(store)) {
    if (key.startsWith(NAMESPACE) && !key.startsWith(PREFIX)) store.removeItem(key)
  }
}

// The last value written under each key. An auto-refresh that changes nothing
// then costs a stringify and a string compare instead of a ~200 KB synchronous
// write to disk-backed storage, every interval, forever.
const written = new Map()

export function readCache(key, fallback = null) {
  const raw = store ? store.getItem(PREFIX + key) : memory.get(key)
  if (raw === null || raw === undefined) return fallback
  try {
    return JSON.parse(raw)
  } catch {
    // A half-written or hand-edited entry must not take the page down on every
    // single load. Drop it and carry on as if the cache had missed.
    dropCache(key)
    return fallback
  }
}

export function writeCache(key, value) {
  const raw = JSON.stringify(value)
  if (raw === undefined) return false // undefined, or a function
  if (written.get(key) === raw) return true

  if (!store) {
    memory.set(key, raw)
    written.set(key, raw)
    return true
  }
  try {
    store.setItem(PREFIX + key, raw)
  } catch {
    // Out of quota. The dashboard snapshot is by far the largest thing in
    // here, so evict our own namespace and retry once; if it still will not
    // fit, run uncached rather than throwing out of a render or an effect.
    clearCache()
    try {
      store.setItem(PREFIX + key, raw)
    } catch {
      return false
    }
  }
  written.set(key, raw)
  return true
}

export function dropCache(key) {
  written.delete(key)
  memory.delete(key)
  store?.removeItem(PREFIX + key)
}

export function clearCache() {
  written.clear()
  memory.clear()
  if (!store) return
  for (const key of Object.keys(store)) {
    if (key.startsWith(NAMESPACE)) store.removeItem(key)
  }
}

/**
 * useState, seeded from the cache and mirrored back into it.
 *
 * For state that changes at human speed — which tab is open, whether the chat
 * drawer is showing. Not for anything that changes per keystroke or per
 * streamed token: that is one storage write per change. Cache those at a
 * natural boundary with writeCache instead.
 */
export function useCached(key, initial) {
  const [value, setValue] = useState(() => readCache(key, initial))
  useEffect(() => {
    writeCache(key, value)
  }, [key, value])
  return [value, setValue]
}
