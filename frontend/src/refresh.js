/**
 * The auto-refresh loop.
 *
 * The dashboard is not the only writer. The chat agent edits the same JSON
 * files, and CLAUDE.md documents hand-editing `data/` from a Claude Code
 * session as a supported workflow. Without polling, the page quietly disagrees
 * with the database until someone thinks to reload it — and a tracker you
 * can't trust to be current is one you stop reading.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

// The backend is local and single-user, so this is about how fast a write from
// somewhere else should surface, not about load. Thirty seconds is shorter
// than it takes to read one card.
export const REFRESH_MS = 30_000

/**
 * Call `onRefresh` on an interval while the tab is visible.
 *
 * Returns `refreshNow` for the manual button, and `refreshing` so the button
 * can say what it is doing.
 */
export function useAutoRefresh(onRefresh, { intervalMs = REFRESH_MS, enabled = true } = {}) {
  const [refreshing, setRefreshing] = useState(false)
  const inFlight = useRef(false)
  const lastRun = useRef(Date.now())

  // Held in a ref so that a new callback identity can never restart the
  // interval — otherwise a parent re-render silently resets the clock and the
  // refresh that was two seconds away never happens.
  const saved = useRef(onRefresh)
  useEffect(() => {
    saved.current = onRefresh
  }, [onRefresh])

  const refreshNow = useCallback(async () => {
    // Overlapping loads would race each other into setData, and the loser
    // still costs a full round trip. A slow backend must not queue up work.
    if (inFlight.current) return
    inFlight.current = true
    setRefreshing(true)
    try {
      await saved.current()
    } finally {
      lastRun.current = Date.now()
      inFlight.current = false
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return undefined

    // A hidden tab is a tab nobody is reading. Polling one left open overnight
    // is ~2,880 pointless requests that still leave stale data on screen at
    // the moment it is looked at, so the work moves to that moment instead.
    const tick = () => {
      if (!document.hidden) refreshNow()
    }
    const onVisibilityChange = () => {
      if (!document.hidden && Date.now() - lastRun.current >= intervalMs) refreshNow()
    }

    const id = setInterval(tick, intervalMs)
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [enabled, intervalMs, refreshNow])

  return { refreshing, refreshNow }
}

/** Re-render the caller on a timer, so an elapsed-time label stays honest
 *  between refreshes rather than freezing at whatever it said last. */
export function useTicker(ms = 5000) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), ms)
    return () => clearInterval(id)
  }, [ms])
}

/** mm:ss under an hour, h:mm:ss over it. */
export function clock(seconds) {
  const s = Math.max(0, Math.round(seconds ?? 0))
  const parts = [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
  return (parts[0] ? parts : parts.slice(1))
    .map((n, i) => (i === 0 ? String(n) : String(n).padStart(2, '0')))
    .join(':')
}

/**
 * Seconds on a problem's stopwatch right now.
 *
 * While running, counted from the banked total and the server's start stamp
 * rather than from `elapsed_seconds`, which is only correct at the instant it
 * was fetched — otherwise the display freezes between 30s polls. Server and
 * browser are the same machine here, so there is no clock skew to correct for.
 */
export function liveSeconds(timer, fallback = 0) {
  if (!timer?.started_at) return fallback
  return (
    (timer.accumulated_seconds ?? 0) +
    Math.max(0, Math.floor((Date.now() - new Date(timer.started_at).getTime()) / 1000))
  )
}

/** "just now" / "40s ago" / "3m ago" — coarser as it gets older, because
 *  nobody needs second precision on something an hour old. */
export function formatAge(at) {
  if (!at) return 'never'
  const seconds = Math.max(0, Math.round((Date.now() - at) / 1000))
  if (seconds < 10) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.round(minutes / 60)}h ago`
}
