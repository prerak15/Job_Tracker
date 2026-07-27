import { useMemo, useState } from 'react'
import { api } from '../api'
import { BarRows, Card, Empty, Field, Pill, Tile, label, pct, since } from './ui'

/** Revision queue — shared by DSA and System Design. */
export function RevisionQueue({ items, onRevisit }) {
  if (!items.length) {
    return <p className="muted small">Nothing due. Everything recent is holding up.</p>
  }
  return (
    <div className="rows">
      {items.map((item) => (
        <div
          key={item.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            paddingBottom: 9,
            borderBottom: '1px solid var(--grid)',
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="row-main" style={{ fontSize: 13 }}>
              {item.title}
            </div>
            <div className="row-sub">
              {item.reason}
              {item.days_since_touched != null && ` · ${since(item.days_since_touched)}`}
            </div>
          </div>
          <button
            className="btn small"
            onClick={() => {
              const outcome = prompt(`How did the redo of "${item.title}" go?`)
              if (outcome === null) return
              const raw = prompt('Confidence now, 1-5?', String(item.confidence ?? 3))
              if (raw === null) return
              onRevisit(item.id, outcome, Number(raw) || null)
            }}
          >
            Log redo
          </button>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- DSA

export default function Dsa({ problems, stats, queue, meta, reload }) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [adding, setAdding] = useState(false)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return problems
      .filter((p) => filter === 'all' || p.status === filter)
      .filter(
        (p) =>
          !needle ||
          p.title.toLowerCase().includes(needle) ||
          p.topics.some((t) => t.toLowerCase().includes(needle)),
      )
      .sort((a, b) => (b.date_started || '').localeCompare(a.date_started || ''))
  }, [problems, search, filter])

  const difficultyRows = meta.dsa_difficulties.map((d) => ({
    label: label(d),
    value: stats.by_difficulty?.[d]?.total ?? 0,
    solved: stats.by_difficulty?.[d]?.solved ?? 0,
    rate: stats.by_difficulty?.[d]?.solve_rate ?? 0,
  }))

  const topicRows = Object.entries(stats.by_topic ?? {})
    .map(([k, v]) => ({ label: k, value: v.total, solved: v.solved, rate: v.solve_rate }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  return (
    <>
      <div className="tiles">
        <Tile label="Problems solved" value={stats.solved ?? 0} note={`${stats.total ?? 0} tracked`} />
        <Tile label="Solve rate" value={pct(stats.solve_rate)} note={`${stats.stuck ?? 0} stuck`} />
        <Tile label="Avg time" value={`${stats.avg_time_minutes ?? 0}m`} note={`${stats.avg_attempts ?? 0} attempts avg`} />
        <Tile label="Hint rate" value={pct(stats.hint_rate)} note="of solved problems" />
        <Tile label="Per week" value={stats.solved_per_week ?? 0} note="last 4 weeks" />
        <Tile label="Due for revision" value={stats.revision_due ?? 0} note={`${stats.issues_logged ?? 0} issues logged`} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        <Card title="By difficulty" sub="How many attempted, and how many landed">
          <BarRows
            items={difficultyRows.filter((r) => r.value > 0)}
            empty="No problems yet."
            formatValue={(i) => `${i.solved}/${i.value} · ${i.rate}%`}
          />
        </Card>

        <Card title="Revision queue" sub="Low confidence, hint-assisted, or going stale">
          <RevisionQueue
            items={queue}
            onRevisit={async (id, outcome, confidence) => {
              await api.dsa.logRevisit(id, { outcome, confidence })
              reload()
            }}
          />
        </Card>

        <Card title="Topics" sub="Coverage by tag — the widest gaps are worth drilling">
          <BarRows
            items={topicRows}
            empty="No topics tagged yet."
            formatValue={(i) => `${i.solved}/${i.value}`}
          />
        </Card>

        <Card title="Weakest topics" sub="Lowest solve rate, most struggle signals">
          {stats.weak_topics?.length ? (
            <div className="rows">
              {stats.weak_topics.map((t) => (
                <div key={t.topic} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                  <span style={{ flex: 1 }}>{t.topic}</span>
                  <span className="row-value">
                    {t.solve_rate}% · {t.issues} issues
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted small">Not enough data yet.</p>
          )}
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="Problems"
          sub={`${visible.length} shown`}
          actions={
            <button className="btn primary" onClick={() => setAdding((v) => !v)}>
              {adding ? 'Cancel' : 'Add problem'}
            </button>
          }
        >
          {adding && (
            <ProblemForm
              meta={meta}
              onSave={async (body) => {
                await api.dsa.create(body)
                setAdding(false)
                reload()
              }}
            />
          )}

          <div className="toolbar">
            <input
              placeholder="Search title or topic…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All statuses</option>
              {meta.dsa_statuses.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </div>

          {visible.length === 0 ? (
            <Empty>No problems match. Tell the assistant what you worked on and it will log it.</Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Problem</th>
                  <th>Difficulty</th>
                  <th>Status</th>
                  <th className="num">Time</th>
                  <th className="num">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((p) => (
                  <ProblemRow
                    key={p.id}
                    problem={p}
                    meta={meta}
                    open={expanded === p.id}
                    onToggle={() => setExpanded(expanded === p.id ? null : p.id)}
                    reload={reload}
                  />
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  )
}

function ProblemRow({ problem, meta, open, onToggle, reload }) {
  const [issue, setIssue] = useState('')

  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">{problem.title}</div>
          <div className="row-sub">
            {label(problem.platform)}
            {problem.topics.length > 0 && ` · ${problem.topics.join(', ')}`}
          </div>
        </td>
        <td>
          <Pill tone="">{problem.difficulty}</Pill>
        </td>
        <td>
          <select
            value={problem.status}
            onClick={(e) => e.stopPropagation()}
            onChange={async (e) => {
              await api.dsa.update(problem.id, { status: e.target.value })
              reload()
            }}
            style={{ width: 'auto', padding: '4px 6px', fontSize: 12 }}
          >
            {meta.dsa_statuses.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </td>
        <td className="num">{problem.time_spent_minutes ? `${problem.time_spent_minutes}m` : '—'}</td>
        <td className="num">{problem.confidence ? `${problem.confidence}/5` : '—'}</td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={5}>
            <div className="detail-inner">
              <div>
                <h4>Timeline</h4>
                <p className="small muted">
                  Started: {problem.date_started ?? '—'}
                  <br />
                  Completed: {problem.date_completed ?? '—'}
                  <br />
                  Attempts: {problem.attempts || '—'}
                  <br />
                  Used a hint: {problem.used_hint ? 'yes' : 'no'}
                </p>
                {problem.url && (
                  <a className="small" href={problem.url} target="_blank" rel="noreferrer">
                    Open problem ↗
                  </a>
                )}
                <div className="field-row" style={{ marginTop: 12 }}>
                  <Field label="Minutes">
                    <input
                      type="number"
                      defaultValue={problem.time_spent_minutes ?? ''}
                      onBlur={async (e) => {
                        await api.dsa.update(problem.id, {
                          time_spent_minutes: Number(e.target.value) || null,
                        })
                        reload()
                      }}
                    />
                  </Field>
                  <Field label="Confidence 1-5">
                    <input
                      type="number"
                      min="1"
                      max="5"
                      defaultValue={problem.confidence ?? ''}
                      onBlur={async (e) => {
                        await api.dsa.update(problem.id, {
                          confidence: Number(e.target.value) || null,
                        })
                        reload()
                      }}
                    />
                  </Field>
                </div>
              </div>

              <div>
                <h4>What went wrong</h4>
                {problem.issues.length === 0 && <p className="muted small">Nothing logged.</p>}
                {problem.issues.map((i, n) => (
                  <div className="list-note" key={n}>
                    <div className="when">{i.date}</div>
                    {i.issue}
                  </div>
                ))}
                <textarea
                  placeholder="What tripped you up?"
                  value={issue}
                  onChange={(e) => setIssue(e.target.value)}
                  style={{ marginTop: 8, minHeight: 54 }}
                />
                <button
                  className="btn small"
                  style={{ marginTop: 8 }}
                  onClick={async () => {
                    if (!issue.trim()) return
                    await api.dsa.logIssue(problem.id, { issue })
                    setIssue('')
                    reload()
                  }}
                >
                  Log issue
                </button>
              </div>

              <div>
                <h4>Solution notes</h4>
                <textarea
                  defaultValue={problem.solution_notes}
                  placeholder="The key insight, so future-you doesn't re-derive it"
                  onBlur={async (e) => {
                    if (e.target.value !== problem.solution_notes) {
                      await api.dsa.update(problem.id, { solution_notes: e.target.value })
                      reload()
                    }
                  }}
                />
                <h4 style={{ marginTop: 14 }}>Revisits</h4>
                {problem.revisits.length === 0 && <p className="muted small">Never redone.</p>}
                {problem.revisits.map((r, n) => (
                  <div className="list-note" key={n}>
                    <div className="when">{r.date}</div>
                    {r.outcome}
                  </div>
                ))}
                <button
                  className="btn small ghost"
                  style={{ marginTop: 10, color: 'var(--critical)' }}
                  onClick={async () => {
                    if (confirm(`Delete "${problem.title}"?`)) {
                      await api.dsa.remove(problem.id)
                      reload()
                    }
                  }}
                >
                  Delete problem
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function ProblemForm({ meta, onSave }) {
  const [form, setForm] = useState({
    title: '',
    platform: 'leetcode',
    difficulty: 'medium',
    status: 'in_progress',
    topics: '',
    url: '',
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: 14,
        marginBottom: 16,
      }}
    >
      <div className="field-row">
        <Field label="Title">
          <input value={form.title} onChange={set('title')} />
        </Field>
        <Field label="Platform">
          <select value={form.platform} onChange={set('platform')}>
            {meta.dsa_platforms.map((p) => (
              <option key={p} value={p}>
                {label(p)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Difficulty">
          <select value={form.difficulty} onChange={set('difficulty')}>
            {meta.dsa_difficulties.map((d) => (
              <option key={d} value={d}>
                {label(d)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={form.status} onChange={set('status')}>
            {meta.dsa_statuses.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="field-row">
        <Field label="Topics (comma separated)">
          <input value={form.topics} onChange={set('topics')} placeholder="dp, binary-search" />
        </Field>
        <Field label="URL">
          <input value={form.url} onChange={set('url')} />
        </Field>
      </div>
      <button
        className="btn primary"
        onClick={() => {
          if (!form.title) return
          onSave({
            ...form,
            url: form.url || null,
            topics: form.topics
              .split(',')
              .map((t) => t.trim())
              .filter(Boolean),
          })
        }}
      >
        Save problem
      </button>
    </div>
  )
}
