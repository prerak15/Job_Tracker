import { useMemo, useState } from 'react'
import { api } from '../api'
import { BarRows, Card, Empty, Meter, Pill, Tile, label, pct, since } from './ui'

/**
 * Pattern revision — the technique axis, across DSA and system design.
 *
 * Everything about progress on this tab is computed by the backend from
 * dsa.json and design.json, so a number here can never disagree with the tab
 * that owns the work. The only things this page writes are the ones nothing
 * else knows: a confidence, a note, a flag, and a logged revisit.
 */

const DOMAIN_LABEL = { dsa: 'DSA', lld: 'LLD', hld: 'HLD' }

// How many never-started patterns the card shows before deferring to the
// table. Same reasoning as dsa.NEXT_UP_LIMIT: a list of twenty things to
// start is a backlog, not a decision.
const UNSTARTED_SHOWN = 6

function Domain({ value }) {
  return <span className="tag">{DOMAIN_LABEL[value] ?? label(value)}</span>
}

/** 1-5, as buttons. A select hides the current value behind a click, and the
 *  rating is the one signal on this page a person actually has to supply. */
function Confidence({ value, onSet }) {
  return (
    <span style={{ display: 'inline-flex', gap: 3 }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          className={`btn small ${n === value ? 'primary' : 'ghost'}`}
          style={{ padding: '2px 7px', minWidth: 0 }}
          title={`Rate this ${n}/5`}
          onClick={() => onSet(n === value ? null : n)}
        >
          {n}
        </button>
      ))}
    </span>
  )
}

export default function Patterns({ patterns, stats, queue, unstarted, reload, askAssistant }) {
  const [domain, setDomain] = useState('all')
  const [state, setState] = useState('all')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(null)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return patterns
      .filter((p) => domain === 'all' || p.domain === domain)
      .filter((p) => state === 'all' || p.state === state)
      .filter(
        (p) =>
          !needle ||
          p.name.toLowerCase().includes(needle) ||
          p.problems.some((q) => q.title.toLowerCase().includes(needle)),
      )
  }, [patterns, domain, state, search])

  const coverageRows = Object.entries(stats.by_domain ?? {})
    .filter(([, v]) => v.patterns > 0)
    .map(([key, v]) => ({
      label: DOMAIN_LABEL[key] ?? key,
      value: v.coverage,
      solved: v.solved,
      total: v.problems,
    }))

  const revise = async (pattern) => {
    const outcome = prompt(`How did re-deriving "${pattern.name}" go?`)
    if (outcome === null) return
    const raw = prompt('Confidence now, 1-5?', String(pattern.confidence ?? 3))
    if (raw === null) return
    await api.patterns.logRevisit(pattern.key, {
      outcome,
      confidence: Number(raw) || null,
    })
    reload()
  }

  if (patterns.length === 0) {
    return (
      <Card
        title="Pattern revision"
        sub="Techniques across DSA and system design, tracked separately from individual problems"
      >
        <Empty>
          <p>Nothing loaded yet.</p>
          <p className="muted small">
            The curriculum is the sixteen patterns from your sheet, plus a starting set of
            LLD/HLD techniques. Loading it never touches what you have already solved —
            progress is read from the DSA and design tabs every time this page opens.
          </p>
          <button
            className="btn primary"
            onClick={async () => {
              await api.patterns.seed()
              reload()
            }}
          >
            Load the curriculum
          </button>
        </Empty>
      </Card>
    )
  }

  return (
    <>
      <div className="tiles">
        <Tile
          label="Patterns"
          value={stats.total ?? 0}
          note={`${stats.by_domain?.dsa?.patterns ?? 0} DSA · ${
            (stats.by_domain?.lld?.patterns ?? 0) + (stats.by_domain?.hld?.patterns ?? 0)
          } design`}
        />
        <Tile
          label="Coverage"
          value={pct(stats.coverage)}
          note={`${stats.solved ?? 0} of ${stats.problems ?? 0} problems`}
          hero
        />
        <Tile
          label="Practiced"
          value={stats.by_state?.practiced ?? 0}
          note={`${stats.by_state?.learning ?? 0} part-way`}
        />
        <Tile
          label="Due for revision"
          value={stats.due ?? 0}
          note={stats.flagged ? `${stats.flagged} flagged by hand` : 'decayed or unrated'}
        />
        <Tile
          label="Not queued"
          value={stats.untracked ?? 0}
          note="catalogue rows with no record yet"
        />
      </div>

      <div
        className="grid"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', marginTop: 16 }}
      >
        {/* Two lists, side by side and never merged. "Decayed" is short and
            actionable; "never started" is long by definition, and folding them
            together buries the revision that is actually due. */}
        <Card
          title="Due for revision"
          sub="Worked before, and since gone quiet, unrated or shaky"
          actions={
            askAssistant &&
            queue.length > 0 && (
              <button
                className="btn small"
                onClick={() =>
                  askAssistant(
                    `Which pattern should I revise first, and what should I re-derive from scratch to prove I still have it?`,
                  )
                }
              >
                Ask
              </button>
            )
          }
        >
          {queue.length === 0 ? (
            <p className="muted small">Nothing due. Everything you have covered is holding up.</p>
          ) : (
            <div className="rows">
              {queue.map((item) => (
                <div key={item.key} className="lead-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="row-main" style={{ fontSize: 13 }}>
                      {item.name} <Domain value={item.domain} />
                    </div>
                    <div className="row-sub">
                      {item.reason} · {item.solved}/{item.total} done
                      {item.days_since_worked != null && ` · last touched ${since(item.days_since_worked)}`}
                    </div>
                    {item.next_problem && (
                      <div className="row-sub">
                        next unsolved:{' '}
                        {item.next_problem.url ? (
                          <a href={item.next_problem.url} target="_blank" rel="noreferrer">
                            {item.next_problem.title}
                          </a>
                        ) : (
                          item.next_problem.title
                        )}
                      </div>
                    )}
                  </div>
                  <button
                    className="btn small"
                    title="Re-derive it, then record how that went"
                    onClick={() => revise(item)}
                  >
                    Log revision
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Not started" sub="Nothing solved in these yet — new ground, not revision">
          {unstarted.length === 0 ? (
            <p className="muted small">Every pattern has something solved in it.</p>
          ) : (
            <div className="rows">
              {/* Capped: from a standing start this list is every pattern, and a
                  card that long stops being read at all. The full set is the
                  table below, filtered to "Untouched". */}
              {unstarted.slice(0, UNSTARTED_SHOWN).map((item) => (
                <div key={item.key} className="lead-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="row-main" style={{ fontSize: 13 }}>
                      {item.name} <Domain value={item.domain} />
                    </div>
                    <div className="row-sub">
                      {item.total} problems listed
                      {item.first_problem && ` · starts at ${item.first_problem.title}`}
                    </div>
                  </div>
                  <button
                    className="btn small ghost"
                    onClick={() => {
                      setState('all')
                      setSearch('')
                      setExpanded(item.key)
                    }}
                  >
                    Open
                  </button>
                </div>
              ))}
              {unstarted.length > UNSTARTED_SHOWN && (
                <p className="muted small" style={{ marginBottom: 0 }}>
                  {unstarted.length - UNSTARTED_SHOWN} more — filter the table below to
                  “Untouched”.
                </p>
              )}
            </div>
          )}
        </Card>

        <Card title="Coverage by domain" sub="Share of each catalogue actually solved">
          <BarRows
            items={coverageRows}
            empty="Nothing loaded."
            formatValue={(item) => `${item.solved}/${item.total} · ${pct(item.value)}`}
          />
          {stats.thinnest?.length > 0 && (
            <>
              <h4 style={{ margin: '14px 0 6px', fontSize: 12 }}>Thinnest started patterns</h4>
              <BarRows
                items={stats.thinnest.map((p) => ({
                  label: p.name,
                  value: p.coverage,
                }))}
                formatValue={(item) => pct(item.value)}
              />
            </>
          )}
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="The catalogue"
          sub={`${visible.length} of ${patterns.length} shown · progress is read live from the DSA and design tabs`}
        >
          <div className="toolbar">
            <input
              placeholder="Search a pattern or a problem…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="all">Both domains</option>
              <option value="dsa">DSA</option>
              <option value="lld">LLD</option>
              <option value="hld">HLD</option>
            </select>
            <select value={state} onChange={(e) => setState(e.target.value)}>
              <option value="all">Any state</option>
              <option value="untouched">Untouched</option>
              <option value="learning">Learning</option>
              <option value="practiced">Practiced</option>
            </select>
          </div>

          {visible.length === 0 ? (
            <Empty>Nothing matches that filter.</Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Pattern</th>
                  <th>State</th>
                  <th>Coverage</th>
                  <th className="num">Done</th>
                  <th>Confidence</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((pattern) => (
                  <PatternRow
                    key={pattern.key}
                    pattern={pattern}
                    open={expanded === pattern.key}
                    onToggle={() =>
                      setExpanded(expanded === pattern.key ? null : pattern.key)
                    }
                    onRevise={() => revise(pattern)}
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

function PatternRow({ pattern, open, onToggle, onRevise, reload }) {
  const set = async (patch) => {
    await api.patterns.update(pattern.key, patch)
    reload()
  }

  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">
            {pattern.name} <Domain value={pattern.domain} />
          </div>
          <div className="row-sub">
            {pattern.total} problems
            {pattern.untracked > 0 && ` · ${pattern.untracked} not queued`}
            {/* Tagged work that isn't on the sheet. Shown, but kept out of the
                coverage figure — see the note in patterns._decorate. */}
            {pattern.extra_solved > 0 && ` · ${pattern.extra_solved} solved off-catalogue`}
            {pattern.due && ` · ${pattern.due_reason}`}
          </div>
        </td>
        <td>
          <Pill>{pattern.state}</Pill>
        </td>
        <td style={{ minWidth: 90 }}>
          <Meter value={pattern.coverage} />
        </td>
        <td className="num">
          {pattern.solved}/{pattern.total}
        </td>
        <td onClick={(e) => e.stopPropagation()}>
          <Confidence value={pattern.confidence} onSet={(n) => set({ confidence: n })} />
        </td>
        <td onClick={(e) => e.stopPropagation()}>
          {/* Disabled while untouched: the backend refuses to call anything
              untouched "due", so a flag there would look set and do nothing. */}
          <button
            className="btn small ghost"
            aria-pressed={pattern.flagged}
            disabled={pattern.state === 'untouched'}
            title={
              pattern.state === 'untouched'
                ? 'Nothing solved here yet — there is nothing to revise'
                : pattern.flagged
                  ? 'Flagged for revision — click to clear'
                  : 'Force this into the revision queue'
            }
            onClick={() => set({ flagged: !pattern.flagged })}
          >
            {pattern.flagged ? 'Flagged' : 'Flag'}
          </button>
        </td>
      </tr>

      {open && (
        <tr className="detail">
          <td colSpan={6}>
            <div className="detail-inner">
              <h4>The idea</h4>
              <p className="small" style={{ maxWidth: '68ch' }}>
                {pattern.idea}
              </p>
              <p className="muted small">
                {pattern.last_worked
                  ? `Last worked ${pattern.last_worked}`
                  : 'Never worked'}
                {pattern.last_revised && ` · last re-derived ${pattern.last_revised}`}
              </p>
              <div style={{ display: 'flex', gap: 8, margin: '10px 0 4px' }}>
                <button className="btn small" onClick={onRevise}>
                  Log revision
                </button>
              </div>

              <h4>Problems</h4>
              <ProblemList pattern={pattern} reload={reload} />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

/** The catalogue rows, under the sheet's own sub-headings where it had them. */
function ProblemList({ pattern, reload }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  // The sheet groups trees and heaps into runs ("Traversal", "2 heaps"). Keep
  // that structure: it is how the list is actually read.
  const groups = []
  pattern.problems.forEach((problem, index) => {
    const name = problem.group ?? ''
    const last = groups[groups.length - 1]
    if (last && last.name === name) last.items.push({ problem, index })
    else groups.push({ name, items: [{ problem, index }] })
  })

  const promote = async (index) => {
    setBusy(index)
    setError(null)
    try {
      // No phase. Stamping the *current* phase onto, say, a tree problem
      // promoted while Phase 2 is in flight would let it jump next_up() as
      // "next in Graph Foundations", which it isn't. Pattern study is a
      // parallel track to the curriculum, so it lands in the backlog and the
      // phase gets set deliberately or not at all.
      await api.patterns.promote(pattern.key, { index })
      reload()
    } catch (err) {
      setError(String(err.message ?? err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      {error && (
        <p className="small" style={{ color: 'var(--critical)' }}>
          {error}
        </p>
      )}
      {groups.map((group) => (
        <div key={group.name || 'ungrouped'} style={{ marginBottom: 10 }}>
          {group.name && (
            <div className="row-sub" style={{ margin: '8px 0 4px', fontWeight: 600 }}>
              {group.name}
            </div>
          )}
          <div className="rows">
            {group.items.map(({ problem, index }) => (
              <div key={`${problem.title}-${index}`} className="lead-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row-main" style={{ fontSize: 13 }}>
                    {problem.url ? (
                      <a href={problem.url} target="_blank" rel="noreferrer">
                        {problem.title}
                      </a>
                    ) : (
                      problem.title
                    )}
                    {problem.challenge && (
                      <span className="tag" title="Marked a challenge problem in the sheet">
                        challenge
                      </span>
                    )}
                  </div>
                  {(problem.platform !== 'none' || problem.refs.length > 0) && (
                    <div className="row-sub">
                      {problem.platform !== 'none' && problem.platform}
                      {problem.refs.map((ref) => (
                        <span key={ref}>
                          {' · '}
                          <a href={ref} target="_blank" rel="noreferrer">
                            notes
                          </a>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {problem.difficulty && <Pill>{problem.difficulty}</Pill>}
                {problem.tracked ? (
                  <Pill>{problem.status}</Pill>
                ) : (
                  <button
                    className="btn small ghost"
                    disabled={busy === index}
                    title="Queue this as a todo in the domain that owns it"
                    onClick={() => promote(index)}
                  >
                    {busy === index ? '…' : 'Queue it'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  )
}
