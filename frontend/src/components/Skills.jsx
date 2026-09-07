import { useMemo, useState } from 'react'
import { api } from '../api'
import { BarRows, Card, Empty, Meter, Pill, Tags, Tile, label, pct } from './ui'

/**
 * Skill gaps, read out of the stored job descriptions.
 *
 * Every number on this tab — demand, which companies asked, whether a resume
 * already claims it, the rank — is computed by the backend from jobs.json and
 * resumes.json on each read. Add a posting on the Applications tab and this
 * board reorders itself; there is nothing here to refresh and nothing that can
 * drift out of agreement with the tabs that own the data.
 *
 * What this page writes is only what nothing else knows: a level (always with
 * evidence behind it), a plan, and a decision to stop chasing something.
 */

const AREA_LABEL = {
  language: 'Language',
  backend: 'Backend',
  data: 'Data',
  ml: 'ML / AI',
  cloud: 'Cloud',
  infra: 'Infra',
  practice: 'Practice',
}

const EFFORT_LABEL = { days: 'days', weeks: 'weeks', months: 'months' }

// How much of the ranked queue the card shows. The point of a ranking is that
// the top of it is the answer; a card listing all twenty-odd open rows is the
// unranked list again, with extra steps.
const QUEUE_SHOWN = 6

function Area({ value }) {
  return <span className="tag">{AREA_LABEL[value] ?? label(value)}</span>
}

export default function Skills({ skills, stats, queue, exposed, declined, reload, askAssistant }) {
  const [area, setArea] = useState('all')
  const [state, setState] = useState('all')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(null)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return skills
      .filter((s) => area === 'all' || s.area === area)
      .filter((s) => state === 'all' || s.state === state)
      .filter(
        (s) =>
          !needle ||
          s.name.toLowerCase().includes(needle) ||
          s.aliases.some((a) => a.toLowerCase().includes(needle)) ||
          s.organisations.some((o) => o.toLowerCase().includes(needle)),
      )
  }, [skills, area, state, search])

  const logEvidence = async (skill) => {
    const note = prompt(
      `What did you actually build or run with ${skill.name}?\n\n` +
        'This becomes the evidence line — it has to be a thing, not a feeling.',
      skill.evidence ?? '',
    )
    if (note === null || !note.trim()) return
    const raw = prompt(
      'Level now?\n0 none · 1 aware · 2 used · 3 built · 4 shipped',
      String(Math.max(skill.level, 1)),
    )
    if (raw === null) return
    await api.skills.logEvidence(skill.key, { note, level: Number(raw) })
    reload()
  }

  const decline = async (skill) => {
    const reason = prompt(
      `Why stop chasing ${skill.name}?\n\n` +
        'Its demand keeps counting either way, so this comes back if more postings ask.',
    )
    if (reason === null || !reason.trim()) return
    await api.skills.decline(skill.key, reason)
    reload()
  }

  if (skills.length === 0) {
    return (
      <Card
        title="Skill gaps"
        sub="What the job descriptions you have saved keep asking for, against what you can supply"
      >
        <Empty>
          <p>Nothing loaded yet.</p>
          <p className="muted small">
            The catalogue starts from the skills your saved postings actually name, plus the
            ones you already have — those are the denominator, without them coverage is a
            percentage of nothing. Demand is read from the job descriptions on every load, so
            the ranking updates itself as you add applications.
          </p>
          <button
            className="btn primary"
            onClick={async () => {
              await api.skills.seed()
              reload()
            }}
          >
            Load the catalogue
          </button>
        </Empty>
      </Card>
    )
  }

  return (
    <>
      <div className="tiles">
        <Tile
          label="JDs read"
          value={stats.jds_read ?? 0}
          note="demand is recomputed from these"
        />
        <Tile
          label="Coverage"
          value={pct(stats.coverage)}
          note={`of the ${stats.in_demand ?? 0} skills they ask for`}
          hero
        />
        <Tile
          label="Open gaps"
          value={stats.open ?? 0}
          note={`${stats.quick_wins ?? 0} closable in days`}
        />
        <Tile
          label="Unbacked claims"
          value={stats.exposed ?? 0}
          note={stats.exposed ? 'already on a resume' : 'nothing overstated'}
        />
        <Tile
          label="Declined"
          value={stats.declined ?? 0}
          note="decided against, demand still counted"
        />
      </div>

      <div
        className="grid"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', marginTop: 16 }}
      >
        <Card
          title="Acquire next"
          sub="Ranked by what the saved postings ask for, how far off you are, and what it costs"
          actions={
            askAssistant &&
            queue.length > 0 && (
              <button
                className="btn small"
                onClick={() =>
                  askAssistant(
                    'Walk me through the top of my skill gap queue — what should I close first, and what exactly would I build to close it?',
                  )
                }
              >
                Ask
              </button>
            )
          }
        >
          {queue.length === 0 ? (
            <p className="muted small">
              Nothing outstanding that the saved postings ask for.
            </p>
          ) : (
            <div className="rows">
              {queue.slice(0, QUEUE_SHOWN).map((item) => (
                <div key={item.key} className="lead-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="row-main" style={{ fontSize: 13 }}>
                      {item.rank}. {item.name} <Area value={item.area} />
                      <span className="muted small"> · {EFFORT_LABEL[item.effort]}</span>
                    </div>
                    {/* The ranking reorders itself whenever a job is added, so
                        it will look wrong eventually. `because` is how it
                        defends itself when it does. */}
                    <div className="row-sub">{item.because.join(' · ')}</div>
                    <div className="row-sub muted">{item.organisations.join(', ')}</div>
                  </div>
                  <button
                    className="btn small"
                    title="Record what you actually did with it"
                    onClick={() => logEvidence(item)}
                  >
                    Log evidence
                  </button>
                </div>
              ))}
              {queue.length > QUEUE_SHOWN && (
                <p className="muted small" style={{ marginBottom: 0 }}>
                  {queue.length - QUEUE_SHOWN} more below — the table is in the same order.
                </p>
              )}
            </div>
          )}
        </Card>

        {/* Deliberately its own card, and deliberately allowed to repeat rows
            from the queue above. "Learn this" and "this claim is unbacked" are
            different actions, and a skill can honestly need both. */}
        <Card
          title="Claimed but unbacked"
          sub="On a resume already, with less than 'used' behind it"
        >
          {exposed.length === 0 ? (
            <p className="muted small">
              Nothing on your resumes is claiming more than you have.
            </p>
          ) : (
            <div className="rows">
              {exposed.map((item) => (
                <div key={item.key} className="lead-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="row-main" style={{ fontSize: 13 }}>
                      {item.name}{' '}
                      {item.on_master && <Pill tone="red">on the master</Pill>}
                    </div>
                    <div className="row-sub">
                      {label(item.level_name)} · claimed on{' '}
                      {item.claimed_on.length === 1
                        ? item.claimed_on[0]
                        : `${item.claimed_on.length} versions`}
                    </div>
                    {item.on_master && (
                      <div className="row-sub muted">
                        The master goes out with every send — fix this one first.
                      </div>
                    )}
                  </div>
                  <button className="btn small ghost" onClick={() => logEvidence(item)}>
                    Back it up
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="What the postings ask for"
          sub="Most-named skills across every saved JD, held or not"
        >
          <BarRows
            items={(stats.top_demand ?? []).map((s) => ({
              label: s.name,
              value: s.demand,
              state: s.state,
            }))}
            empty="No job descriptions stored yet."
            formatValue={(item) => `${item.value} · ${label(item.state)}`}
          />
          {declined.length > 0 && (
            <>
              <h4 style={{ margin: '14px 0 6px', fontSize: 12 }}>Decided against</h4>
              <div className="rows">
                {declined.map((item) => (
                  <div key={item.key} className="row-item">
                    <span className="row-label" title={item.organisations.join(', ')}>
                      {item.name}
                    </span>
                    <span className="row-value">
                      {item.demand} JD{item.demand === 1 ? '' : 's'}
                    </span>
                  </div>
                ))}
              </div>
              <p className="muted small" style={{ marginTop: 6, marginBottom: 0 }}>
                Demand still counts against these, so a decision made when one posting
                wanted it comes back if four more arrive.
              </p>
            </>
          )}
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="The board"
          sub={`${visible.length} of ${skills.length} shown · demand and claims are read live from the Applications and Resumes tabs`}
        >
          <div className="toolbar">
            <input
              placeholder="Search a skill, an alias or a company…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select value={area} onChange={(e) => setArea(e.target.value)}>
              <option value="all">Every area</option>
              {Object.entries(AREA_LABEL).map(([key, text]) => (
                <option key={key} value={key}>
                  {text}
                </option>
              ))}
            </select>
            <select value={state} onChange={(e) => setState(e.target.value)}>
              <option value="all">Any state</option>
              <option value="missing">Missing</option>
              <option value="learning">Learning</option>
              <option value="exposed">Exposed</option>
              <option value="have">Have</option>
              <option value="declined">Declined</option>
            </select>
          </div>

          {visible.length === 0 ? (
            <Empty>Nothing matches that filter.</Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Skill</th>
                  <th>State</th>
                  <th>Level</th>
                  <th className="num">JDs</th>
                  <th>Effort</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {[...visible]
                  .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
                  .map((skill) => (
                    <SkillRow
                      key={skill.key}
                      skill={skill}
                      open={expanded === skill.key}
                      onToggle={() => setExpanded(expanded === skill.key ? null : skill.key)}
                      onEvidence={() => logEvidence(skill)}
                      onDecline={() => decline(skill)}
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

function SkillRow({ skill, open, onToggle, onEvidence, onDecline, reload }) {
  const set = async (patch) => {
    await api.skills.update(skill.key, patch)
    reload()
  }

  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">
            {skill.name} <Area value={skill.area} />
          </div>
          <div className="row-sub">
            {skill.demand > 0
              ? skill.organisations.slice(0, 4).join(', ') +
                (skill.organisations.length > 4
                  ? ` +${skill.organisations.length - 4}`
                  : '')
              : 'nothing on file asks for it'}
          </div>
        </td>
        <td>
          <Pill>{skill.state}</Pill>
        </td>
        <td style={{ minWidth: 90 }}>
          <Meter value={skill.level} max={skill.target_level || 4} />
          {/* The arrow is only worth showing while there is somewhere to go.
              "shipped → built" on a skill past its target, and any target at
              all on one you have decided against, are noise. */}
          <span className="muted small">
            {skill.state === 'declined'
              ? 'not being chased'
              : skill.gap > 0
                ? `${label(skill.level_name)} → ${label(skill.target_name)}`
                : label(skill.level_name)}
          </span>
        </td>
        <td className="num">
          {skill.demand}
          {skill.demand_live > 0 && skill.demand_live !== skill.demand && (
            <span className="muted small"> ({skill.demand_live} live)</span>
          )}
        </td>
        <td>{EFFORT_LABEL[skill.effort]}</td>
        <td onClick={(e) => e.stopPropagation()}>
          <button className="btn small ghost" onClick={onEvidence}>
            Log evidence
          </button>
        </td>
      </tr>

      {open && (
        <tr className="detail">
          <td colSpan={6}>
            <div className="detail-inner">
              {skill.plan && (
                <>
                  <h4>The closing move</h4>
                  <p className="small" style={{ maxWidth: '68ch' }}>
                    {skill.plan}
                  </p>
                </>
              )}
              {skill.evidence && (
                <>
                  <h4>Evidence</h4>
                  <p className="small" style={{ maxWidth: '68ch' }}>
                    {skill.evidence}
                  </p>
                </>
              )}
              {skill.notes && <p className="muted small">{skill.notes}</p>}

              <h4>Who asked for it</h4>
              {skill.mentions.length === 0 ? (
                <p className="muted small">
                  Nothing on file. Its rank comes from nowhere until a posting names it.
                </p>
              ) : (
                <div className="rows">
                  {skill.mentions.map((m) => (
                    <div key={m.job_id} className="row-item">
                      <span className="row-label" title={m.job_title ?? ''}>
                        {m.organisation}
                      </span>
                      <span className="row-value">
                        <Pill>{m.status}</Pill>{' '}
                        <span className="muted small">“{m.matched}”</span>
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {skill.claimed && (
                <>
                  <h4>Claimed on</h4>
                  <p className="small">
                    {skill.claimed_on.map((c) => c.name).join(' · ')}
                  </p>
                </>
              )}

              <h4>Matched by</h4>
              <p className="small">
                <Tags items={skill.aliases} />
              </p>

              <div style={{ display: 'flex', gap: 8, margin: '10px 0 4px' }}>
                <button className="btn small" onClick={onEvidence}>
                  Log evidence
                </button>
                {skill.status !== 'declined' ? (
                  <button
                    className="btn small ghost"
                    title="Stop chasing it — the demand keeps counting"
                    onClick={onDecline}
                  >
                    Decline
                  </button>
                ) : (
                  <button
                    className="btn small ghost"
                    onClick={() => set({ status: 'wanted' })}
                  >
                    Put it back
                  </button>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
