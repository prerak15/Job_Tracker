import { useMemo, useState } from 'react'
import { api } from '../api'
import { RevisionQueue } from './Practice'
import { BarRows, Card, Empty, Field, Pill, Tags, Tile, label, pct } from './ui'

export default function SystemDesign({ topics, stats, queue, meta, reload }) {
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [adding, setAdding] = useState(false)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return topics
      .filter((t) => kind === 'all' || t.kind === kind)
      .filter(
        (t) =>
          !needle ||
          t.title.toLowerCase().includes(needle) ||
          t.concepts.some((c) => c.toLowerCase().includes(needle)),
      )
      .sort((a, b) => (b.date_started || '').localeCompare(a.date_started || ''))
  }, [topics, search, kind])

  const kindRows = meta.design_kinds.map((k) => ({
    label: k.toUpperCase(),
    value: stats.by_kind?.[k]?.total ?? 0,
    practiced: stats.by_kind?.[k]?.practiced ?? 0,
    rate: stats.by_kind?.[k]?.completion_rate ?? 0,
  }))

  const conceptRows = Object.entries(stats.by_concept ?? {})
    .map(([k, v]) => ({ label: k, value: v.total, practiced: v.practiced }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10)

  return (
    <>
      <div className="tiles">
        <Tile label="Topics practiced" value={stats.practiced ?? 0} note={`${stats.total ?? 0} tracked`} />
        <Tile label="Completion" value={pct(stats.completion_rate)} note={`${stats.stuck ?? 0} stuck`} />
        <Tile label="HLD" value={stats.by_kind?.hld?.practiced ?? 0} note={`of ${stats.by_kind?.hld?.total ?? 0} high-level`} />
        <Tile label="LLD" value={stats.by_kind?.lld?.practiced ?? 0} note={`of ${stats.by_kind?.lld?.total ?? 0} low-level`} />
        <Tile label="Avg time" value={`${stats.avg_time_minutes ?? 0}m`} note={`${stats.artifacts ?? 0} artifacts`} />
        <Tile label="Due for revision" value={stats.revision_due ?? 0} note={`${stats.issues_logged ?? 0} issues logged`} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        <Card title="HLD vs LLD" sub="Practiced means you can produce it unaided">
          <BarRows
            items={kindRows.filter((r) => r.value > 0)}
            empty="No topics yet."
            formatValue={(i) => `${i.practiced}/${i.value} · ${i.rate}%`}
          />
        </Card>

        <Card title="Revision queue" sub="Shaky, unresolved, or going stale">
          <RevisionQueue
            items={queue}
            onRevisit={async (id, outcome, confidence) => {
              await api.design.logRevisit(id, { outcome, confidence })
              reload()
            }}
          />
        </Card>

        <Card title="Concepts" sub="Coverage across the ideas that recur in interviews">
          <BarRows
            items={conceptRows}
            empty="No concepts tagged yet."
            formatValue={(i) => `${i.practiced}/${i.value}`}
          />
        </Card>

        <Card title="Weakest concepts" sub="Lowest completion, most open issues">
          {stats.weak_concepts?.length ? (
            <div className="rows">
              {stats.weak_concepts.map((c) => (
                <div key={c.concept} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                  <span style={{ flex: 1 }}>{c.concept}</span>
                  <span className="row-value">
                    {c.completion_rate}% · {c.issues} issues
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
          title="Design topics"
          sub={`${visible.length} shown`}
          actions={
            <button className="btn primary" onClick={() => setAdding((v) => !v)}>
              {adding ? 'Cancel' : 'Add topic'}
            </button>
          }
        >
          {adding && (
            <TopicForm
              meta={meta}
              onSave={async (body) => {
                await api.design.create(body)
                setAdding(false)
                reload()
              }}
            />
          )}

          <div className="toolbar">
            <input
              placeholder="Search title or concept…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="all">HLD and LLD</option>
              {meta.design_kinds.map((k) => (
                <option key={k} value={k}>
                  {k.toUpperCase()} only
                </option>
              ))}
            </select>
          </div>

          {visible.length === 0 ? (
            <Empty>
              No topics match. Tell the assistant what you studied and it will record it.
            </Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Topic</th>
                  <th>Kind</th>
                  <th>Status</th>
                  <th className="num">Time</th>
                  <th className="num">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((t) => (
                  <TopicRow
                    key={t.id}
                    topic={t}
                    meta={meta}
                    open={expanded === t.id}
                    onToggle={() => setExpanded(expanded === t.id ? null : t.id)}
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

function TopicRow({ topic, meta, open, onToggle, reload }) {
  const [issue, setIssue] = useState('')
  const [artifact, setArtifact] = useState({ type: 'diagram', path_or_url: '' })

  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">{topic.title}</div>
          <div className="row-sub">
            {topic.source || 'No source'}
            {topic.concepts.length > 0 && ` · ${topic.concepts.join(', ')}`}
          </div>
        </td>
        <td>
          <Pill tone="">{topic.kind.toUpperCase()}</Pill>
        </td>
        <td>
          <select
            value={topic.status}
            onClick={(e) => e.stopPropagation()}
            onChange={async (e) => {
              await api.design.update(topic.id, { status: e.target.value })
              reload()
            }}
            style={{ width: 'auto', padding: '4px 6px', fontSize: 12 }}
          >
            {meta.design_statuses.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </td>
        <td className="num">{topic.time_spent_minutes ? `${topic.time_spent_minutes}m` : '—'}</td>
        <td className="num">{topic.confidence ? `${topic.confidence}/5` : '—'}</td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={5}>
            <div className="detail-inner">
              <div>
                <h4>Vocabulary</h4>
                <div className="small" style={{ marginBottom: 8 }}>
                  <div className="muted" style={{ marginBottom: 3 }}>
                    Concepts
                  </div>
                  <Tags items={topic.concepts} />
                </div>
                <div className="small" style={{ marginBottom: 8 }}>
                  <div className="muted" style={{ marginBottom: 3 }}>
                    Components
                  </div>
                  <Tags items={topic.components} />
                </div>
                <div className="small">
                  <div className="muted" style={{ marginBottom: 3 }}>
                    Patterns
                  </div>
                  <Tags items={topic.patterns} />
                </div>
                <p className="small muted" style={{ marginTop: 12 }}>
                  Started: {topic.date_started ?? '—'}
                  <br />
                  Completed: {topic.date_completed ?? '—'}
                </p>
              </div>

              <div>
                <h4>Tradeoffs</h4>
                <textarea
                  defaultValue={topic.tradeoffs}
                  placeholder="What you chose, and why you'd defend it"
                  onBlur={async (e) => {
                    if (e.target.value !== topic.tradeoffs) {
                      await api.design.update(topic.id, { tradeoffs: e.target.value })
                      reload()
                    }
                  }}
                />
                <h4 style={{ marginTop: 14 }}>Notes</h4>
                <textarea
                  defaultValue={topic.notes}
                  onBlur={async (e) => {
                    if (e.target.value !== topic.notes) {
                      await api.design.update(topic.id, { notes: e.target.value })
                      reload()
                    }
                  }}
                />
              </div>

              <div>
                <h4>What was hard</h4>
                {topic.issues.length === 0 && <p className="muted small">Nothing logged.</p>}
                {topic.issues.map((i, n) => (
                  <div className="list-note" key={n}>
                    <div className="when">{i.date}</div>
                    {i.issue}
                  </div>
                ))}
                <textarea
                  placeholder="The part you couldn't justify…"
                  value={issue}
                  onChange={(e) => setIssue(e.target.value)}
                  style={{ marginTop: 8, minHeight: 54 }}
                />
                <button
                  className="btn small"
                  style={{ marginTop: 8 }}
                  onClick={async () => {
                    if (!issue.trim()) return
                    await api.design.logIssue(topic.id, { issue })
                    setIssue('')
                    reload()
                  }}
                >
                  Log issue
                </button>
              </div>

              <div>
                <h4>Artifacts</h4>
                {topic.artifacts.length === 0 && <p className="muted small">None attached.</p>}
                {topic.artifacts.map((a, n) => (
                  <div className="list-note" key={n}>
                    <span className="tag">{a.type}</span> {a.path_or_url}
                  </div>
                ))}
                <div className="field-row" style={{ marginTop: 8 }}>
                  <select
                    value={artifact.type}
                    onChange={(e) => setArtifact({ ...artifact, type: e.target.value })}
                  >
                    {meta.artifact_types.map((t) => (
                      <option key={t} value={t}>
                        {label(t)}
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder="Path or URL"
                    value={artifact.path_or_url}
                    onChange={(e) => setArtifact({ ...artifact, path_or_url: e.target.value })}
                  />
                </div>
                <button
                  className="btn small"
                  style={{ marginTop: 8 }}
                  onClick={async () => {
                    if (!artifact.path_or_url.trim()) return
                    await api.design.addArtifact(topic.id, artifact)
                    setArtifact({ type: 'diagram', path_or_url: '' })
                    reload()
                  }}
                >
                  Attach
                </button>

                <h4 style={{ marginTop: 14 }}>Revisits</h4>
                {topic.revisits.length === 0 && <p className="muted small">Never re-derived.</p>}
                {topic.revisits.map((r, n) => (
                  <div className="list-note" key={n}>
                    <div className="when">{r.date}</div>
                    {r.outcome}
                  </div>
                ))}
                <button
                  className="btn small ghost"
                  style={{ marginTop: 10, color: 'var(--critical)' }}
                  onClick={async () => {
                    if (confirm(`Delete "${topic.title}"?`)) {
                      await api.design.remove(topic.id)
                      reload()
                    }
                  }}
                >
                  Delete topic
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function TopicForm({ meta, onSave }) {
  const [form, setForm] = useState({
    title: '',
    kind: 'hld',
    status: 'studying',
    source: '',
    concepts: '',
    components: '',
    patterns: '',
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const listOf = (s) =>
    s
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)

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
          <input value={form.title} onChange={set('title')} placeholder="Design a URL shortener" />
        </Field>
        <Field label="Kind">
          <select value={form.kind} onChange={set('kind')}>
            {meta.design_kinds.map((k) => (
              <option key={k} value={k}>
                {k.toUpperCase()}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={form.status} onChange={set('status')}>
            {meta.design_statuses.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Source">
          <input value={form.source} onChange={set('source')} placeholder="DDIA ch.6, mock…" />
        </Field>
      </div>
      <div className="field-row">
        <Field label="Concepts">
          <input value={form.concepts} onChange={set('concepts')} placeholder="sharding, caching" />
        </Field>
        <Field label="Components">
          <input value={form.components} onChange={set('components')} placeholder="redis, kafka" />
        </Field>
        <Field label="Patterns">
          <input value={form.patterns} onChange={set('patterns')} placeholder="strategy, factory" />
        </Field>
      </div>
      <button
        className="btn primary"
        onClick={() => {
          if (!form.title) return
          onSave({
            ...form,
            source: form.source || null,
            concepts: listOf(form.concepts),
            components: listOf(form.components),
            patterns: listOf(form.patterns),
          })
        }}
      >
        Save topic
      </button>
    </div>
  )
}
