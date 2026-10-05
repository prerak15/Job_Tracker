import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { CACHE_KEYS, readCache, useCached, writeCache } from './cache'
import { clock, formatAge, liveSeconds, REFRESH_MS, useAutoRefresh, useTicker } from './refresh'
import Applications from './components/Applications'
import ChatPanel from './components/ChatPanel'
import Companies from './components/Companies'
import OpenRoles from './components/OpenRoles'
import Dsa from './components/Practice'
import Patterns from './components/Patterns'
import Resumes from './components/Resumes'
import Skills from './components/Skills'
import SystemDesign from './components/SystemDesign'

const TABS = [
  { id: 'applications', label: 'Applications' },
  { id: 'companies', label: 'Companies' },
  { id: 'roles', label: 'Open roles' },
  { id: 'dsa', label: 'DSA' },
  { id: 'design', label: 'System Design' },
  { id: 'patterns', label: 'Patterns' },
  { id: 'skills', label: 'Skills' },
  { id: 'resumes', label: 'Resumes' },
]

const EMPTY = {
  meta: null,
  jobs: [],
  stats: {},
  followups: [],
  resumes: [],
  resumeStats: {},
  problems: [],
  dsaStats: {},
  dsaQueue: [],
  dsaNextUp: [],
  dsaCoach: { pick: null, reason: '', because: [], unlocked: [], on_hold: [] },
  topics: [],
  designStats: {},
  designQueue: [],
  patterns: [],
  patternStats: {},
  patternQueue: [],
  patternUnstarted: [],
  prep: { phases: [], standing_issues: [], profile: {} },
  readiness: {},
  companies: [],
  companyStats: {},
  skills: [],
  skillStats: {},
  skillQueue: [],
  skillExposed: [],
  skillDeclined: [],
}

export default function App() {
  const [tab, setTab] = useCached(CACHE_KEYS.tab, TABS[0].id)
  const [chatOpen, setChatOpen] = useCached(CACHE_KEYS.chatOpen, true)
  const [autoRefresh, setAutoRefresh] = useCached(CACHE_KEYS.autoRefresh, true)
  const [chatPrompt, setChatPrompt] = useState(null)

  // The snapshot is read exactly once, at mount. Reading it in the render body
  // would parse ~200 KB of JSON on every keystroke, and nothing can change it
  // underneath us anyway.
  const boot = useRef(null)
  if (!boot.current) {
    boot.current = {
      // Spread over EMPTY so a snapshot written before a field existed cannot
      // hand a child `undefined` where it expects a list. CACHE_VERSION in
      // cache.js is the tool for shape changes this can't absorb.
      data: { ...EMPTY, ...readCache(CACHE_KEYS.dashboard) },
      at: readCache(CACHE_KEYS.dashboardAt),
    }
  }

  const [data, setData] = useState(boot.current.data)
  const [lastUpdated, setLastUpdated] = useState(boot.current.at)
  const [error, setError] = useState(null)
  // A cache hit means there is already a page to show, so no loading state.
  const [loading, setLoading] = useState(!boot.current.data.meta)

  // A tab id from an older build must not leave the page blank.
  const activeTab = TABS.some((t) => t.id === tab) ? tab : TABS[0].id

  // Dashboard buttons hand a ready-made question to the assistant. The token
  // makes repeat clicks distinct so the same prompt can be sent twice.
  // setChatOpen is a useState setter under useCached, so it is stable — it is
  // listed because the linter can't see through the hook to know that.
  const askAssistant = useCallback(
    (text) => {
      setChatOpen(true)
      setChatPrompt({ text, token: Date.now() })
    },
    [setChatOpen],
  )

  const reload = useCallback(async () => {
    try {
      const [
        meta,
        jobs,
        stats,
        followups,
        resumes,
        resumeStats,
        problems,
        dsaStats,
        dsaQueue,
        dsaNextUp,
        dsaCoach,
        topics,
        designStats,
        designQueue,
        patternList,
        patternStats,
        patternQueue,
        patternUnstarted,
        prep,
        readiness,
        companies,
        companyStats,
        skillList,
        skillStats,
        skillQueue,
        skillExposed,
        skillDeclined,
      ] = await Promise.all([
        api.meta(),
        api.jobs.list(),
        api.jobs.stats(),
        api.jobs.followupSuggestions(),
        api.resumes.list(),
        api.resumes.stats(),
        api.dsa.list(),
        api.dsa.stats(),
        api.dsa.revisionQueue(),
        api.dsa.nextUp(),
        api.dsa.coach(),
        api.design.list(),
        api.design.stats(),
        api.design.revisionQueue(),
        api.patterns.list(),
        api.patterns.stats(),
        api.patterns.revisionQueue(),
        api.patterns.unstarted(),
        api.prep.get(),
        api.prep.readiness(),
        api.companies.list(),
        api.companies.stats(),
        api.skills.list(),
        api.skills.stats(),
        api.skills.gapQueue(),
        api.skills.exposed(),
        api.skills.declined(),
      ])
      const next = {
        meta,
        jobs,
        stats,
        followups,
        resumes,
        resumeStats,
        problems,
        dsaStats,
        dsaQueue,
        dsaNextUp,
        dsaCoach,
        topics,
        designStats,
        designQueue,
        patterns: patternList,
        patternStats,
        patternQueue,
        patternUnstarted,
        prep,
        readiness,
        companies,
        companyStats,
        skills: skillList,
        skillStats,
        skillQueue,
        skillExposed,
        skillDeclined,
      }
      setData(next)
      setLastUpdated(Date.now())
      // This snapshot is what makes a browser refresh redraw the page you were
      // on instead of "Loading…". The timestamp is a separate key on purpose:
      // folded into the payload it would change every poll and defeat the
      // cache's unchanged-value check, turning every tick into a 200 KB write.
      writeCache(CACHE_KEYS.dashboard, next)
      writeCache(CACHE_KEYS.dashboardAt, Date.now())
      setError(null)
    } catch (err) {
      // Note what failed but keep whatever is on screen. A dropped poll must
      // not replace a working page with an error card — the topbar says the
      // data is stale, and the next tick recovers on its own.
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  const { refreshing, refreshNow } = useAutoRefresh(reload, { enabled: autoRefresh })

  useEffect(() => {
    reload()
  }, [reload])

  const counts = {
    applications: data.stats.active ?? 0,
    companies: data.companyStats.targets ?? 0,
    dsa: data.dsaStats.solved ?? 0,
    design: data.designStats.practiced ?? 0,
    patterns: data.patternStats.by_state?.practiced ?? 0,
    skills: data.skillStats.open ?? 0,
    resumes: data.resumeStats.total_versions ?? 0,
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Job Tracker</span>
        <nav className="tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              className="tab"
              aria-selected={activeTab === t.id}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              <span className="count">{counts[t.id]}</span>
            </button>
          ))}
        </nav>
        {data.followups.length > 0 && (
          <span className="pill orange">
            {data.followups.length} follow-up{data.followups.length === 1 ? '' : 's'} due
          </span>
        )}
        {/* A running stopwatch you can only see on one tab is a stopwatch you
            forget to stop, and a forgotten one is what ruins the average. */}
        {data.dsaStats.timer_running && (
          <RunningTimer running={data.dsaStats.timer_running} onOpen={() => setTab('dsa')} />
        )}
        <RefreshStatus
          lastUpdated={lastUpdated}
          refreshing={refreshing}
          stale={Boolean(error) && Boolean(data.meta)}
          auto={autoRefresh}
          onToggleAuto={() => setAutoRefresh((v) => !v)}
          onRefresh={refreshNow}
        />
        <button className="btn" onClick={() => setChatOpen((v) => !v)}>
          {chatOpen ? 'Hide assistant' : 'Ask assistant'}
        </button>
      </header>

      <div className="layout">
        <main className={`main ${chatOpen ? 'with-chat' : ''}`}>
          {/* Only when there is nothing to show. With a cached page on screen
              the topbar's "stale" marker is the honest signal — blanking a
              readable dashboard over one dropped poll helps nobody. */}
          {error && !data.meta && (
            <div className="card" style={{ borderColor: 'var(--critical)', marginBottom: 16 }}>
              <strong>Can&apos;t reach the backend.</strong>
              <p className="small muted" style={{ marginBottom: 0 }}>
                {error} — start it with <code>uvicorn main:app --reload</code> from the backend
                folder.
              </p>
            </div>
          )}

          {loading || !data.meta ? (
            <p className="muted">Loading…</p>
          ) : (
            <>
              {activeTab === 'applications' && (
                <Applications
                  jobs={data.jobs}
                  stats={data.stats}
                  followups={data.followups}
                  meta={data.meta}
                  resumes={data.resumes}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {activeTab === 'companies' && (
                <Companies
                  companies={data.companies}
                  stats={data.companyStats}
                  meta={data.meta}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {activeTab === 'roles' && (
                <OpenRoles
                  companies={data.companies}
                  meta={data.meta}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {activeTab === 'dsa' && (
                <Dsa
                  problems={data.problems}
                  stats={data.dsaStats}
                  queue={data.dsaQueue}
                  nextUp={data.dsaNextUp}
                  coach={data.dsaCoach}
                  prep={data.prep}
                  readiness={data.readiness}
                  meta={data.meta}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {activeTab === 'design' && (
                <SystemDesign
                  topics={data.topics}
                  stats={data.designStats}
                  queue={data.designQueue}
                  meta={data.meta}
                  reload={reload}
                />
              )}
              {activeTab === 'patterns' && (
                <Patterns
                  patterns={data.patterns}
                  stats={data.patternStats}
                  queue={data.patternQueue}
                  unstarted={data.patternUnstarted}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {activeTab === 'skills' && (
                <Skills
                  skills={data.skills}
                  stats={data.skillStats}
                  queue={data.skillQueue}
                  exposed={data.skillExposed}
                  declined={data.skillDeclined}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {activeTab === 'resumes' && (
                <Resumes
                  resumes={data.resumes}
                  stats={data.resumeStats}
                  jobs={data.jobs}
                  reload={reload}
                />
              )}
            </>
          )}
        </main>

        {chatOpen && (
          <ChatPanel
            onClose={() => setChatOpen(false)}
            onDataChanged={reload}
            prompt={chatPrompt}
          />
        )}
      </div>
    </div>
  )
}

/** Live stopwatch chip. Its own component so the per-second tick re-renders one
 *  pill rather than the whole dashboard. */
function RunningTimer({ running, onOpen }) {
  useTicker(1000)
  return (
    <button
      className="pill orange"
      title={`Timing ${running.title} — click to open`}
      onClick={onOpen}
      style={{ fontVariantNumeric: 'tabular-nums' }}
    >
      ● {clock(liveSeconds(running.timer, running.elapsed_seconds))}
    </button>
  )
}

/** Refresh state, in words. Auto-refresh that gives no sign it is running is
 *  indistinguishable from a page that quietly stopped updating, so the age of
 *  the data is always on screen — and always switchable off, because content
 *  changing under someone who is reading it is its own kind of rude. */
function RefreshStatus({ lastUpdated, refreshing, stale, auto, onToggleAuto, onRefresh }) {
  useTicker(5000)
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span
        className="small muted"
        style={stale ? { color: 'var(--critical)' } : undefined}
        title={stale ? "Can't reach the backend — showing the last good load." : undefined}
      >
        {stale ? 'stale · offline' : `updated ${formatAge(lastUpdated)}`}
      </span>
      <button className="btn small ghost" onClick={onRefresh} disabled={refreshing}>
        {refreshing ? 'Refreshing…' : 'Refresh'}
      </button>
      <button
        className="btn small ghost"
        aria-pressed={auto}
        title={`Auto-refresh every ${REFRESH_MS / 1000}s while this tab is visible`}
        onClick={onToggleAuto}
      >
        Auto {auto ? 'on' : 'off'}
      </button>
    </span>
  )
}
