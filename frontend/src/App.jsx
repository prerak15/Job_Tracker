import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import Applications from './components/Applications'
import ChatPanel from './components/ChatPanel'
import Dsa from './components/Practice'
import Resumes from './components/Resumes'
import SystemDesign from './components/SystemDesign'

const TABS = [
  { id: 'applications', label: 'Applications' },
  { id: 'dsa', label: 'DSA' },
  { id: 'design', label: 'System Design' },
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
  topics: [],
  designStats: {},
  designQueue: [],
  prep: { phases: [], standing_issues: [], profile: {} },
  readiness: {},
}

export default function App() {
  const [tab, setTab] = useState('applications')
  const [chatOpen, setChatOpen] = useState(true)
  const [data, setData] = useState(EMPTY)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [chatPrompt, setChatPrompt] = useState(null)

  // Dashboard buttons hand a ready-made question to the assistant. The token
  // makes repeat clicks distinct so the same prompt can be sent twice.
  const askAssistant = useCallback((text) => {
    setChatOpen(true)
    setChatPrompt({ text, token: Date.now() })
  }, [])

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
        topics,
        designStats,
        designQueue,
        prep,
        readiness,
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
        api.design.list(),
        api.design.stats(),
        api.design.revisionQueue(),
        api.prep.get(),
        api.prep.readiness(),
      ])
      setData({
        meta,
        jobs,
        stats,
        followups,
        resumes,
        resumeStats,
        problems,
        dsaStats,
        dsaQueue,
        topics,
        designStats,
        designQueue,
        prep,
        readiness,
      })
      setError(null)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const counts = {
    applications: data.stats.active ?? 0,
    dsa: data.dsaStats.solved ?? 0,
    design: data.designStats.practiced ?? 0,
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
              aria-selected={tab === t.id}
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
        <button className="btn" onClick={() => setChatOpen((v) => !v)}>
          {chatOpen ? 'Hide assistant' : 'Ask assistant'}
        </button>
      </header>

      <div className="layout">
        <main className={`main ${chatOpen ? 'with-chat' : ''}`}>
          {error && (
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
              {tab === 'applications' && (
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
              {tab === 'dsa' && (
                <Dsa
                  problems={data.problems}
                  stats={data.dsaStats}
                  queue={data.dsaQueue}
                  prep={data.prep}
                  readiness={data.readiness}
                  meta={data.meta}
                  reload={reload}
                  askAssistant={askAssistant}
                />
              )}
              {tab === 'design' && (
                <SystemDesign
                  topics={data.topics}
                  stats={data.designStats}
                  queue={data.designQueue}
                  meta={data.meta}
                  reload={reload}
                />
              )}
              {tab === 'resumes' && (
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
