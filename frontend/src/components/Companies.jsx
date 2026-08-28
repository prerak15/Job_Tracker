import { useMemo, useState } from 'react'
import { api } from '../api'
import { BarRows, Card, Empty, Field, Pill, Tags, Tile, label, pct } from './ui'

// What a SWE / AI-ML search looks like by default. Deliberately broad — the
// backend already strips sales and recruiting titles, so the cost of a loose
// keyword here is low and the cost of missing a role is high.
const DEFAULT_KEYWORDS = 'engineer, software, developer, sde, backend, ai, ml, data'

export default function Companies({ companies, stats, meta, reload, askAssistant }) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [tier, setTier] = useState('all')
  const [status, setStatus] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [adding, setAdding] = useState(false)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return companies
      .filter((c) => category === 'all' || c.category === category)
      .filter((c) => tier === 'all' || c.tier === tier)
      .filter((c) => status === 'all' || c.board_column === status)
      .filter(
        (c) =>
          !needle ||
          c.name.toLowerCase().includes(needle) ||
          c.aliases.some((a) => a.toLowerCase().includes(needle)) ||
          c.tech_stack.some((t) => t.toLowerCase().includes(needle)) ||
          c.locations.some((l) => l.toLowerCase().includes(needle)),
      )
  }, [companies, search, category, tier, status])

  const tierRows = (meta.company_tiers ?? [])
    .map((t) => ({ label: t, value: stats.by_tier?.[t] ?? 0 }))
    .filter((r) => r.value > 0)

  const locationRows = Object.entries(stats.by_location ?? {})
    .map(([k, v]) => ({ label: k, value: v }))
    .slice(0, 8)

  return (
    <>
      <div className="tiles">
        <Tile label="On the board" value={stats.total ?? 0} note={`${stats.by_category?.startup ?? 0} startups`} />
        <Tile label="Targets" value={stats.targets ?? 0} note={`${stats.untouched_targets ?? 0} with nothing sent`} />
        <Tile label="Applied to" value={stats.applied_to ?? 0} note={`${stats.leads_open ?? 0} open leads`} />
        <Tile label="Searchable boards" value={stats.with_ats ?? 0} note={`${pct(stats.ats_coverage)} of the board`} />
        <Tile label="Never checked" value={stats.never_checked ?? 0} note="wired but never searched" />
      </div>

      <Discovery companies={companies} meta={meta} reload={reload} />

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', marginTop: 16 }}>
        <Card title="By tier" sub="The interview bar you'd be preparing for">
          <BarRows items={tierRows} empty="Seed the board to get started." />
        </Card>
        <Card title="Where they hire" sub="Cities across the whole board">
          <BarRows items={locationRows} empty="No locations recorded." />
        </Card>
        <Card
          title="Targets with nothing sent"
          sub="Companies you called targets and never applied to"
          actions={
            askAssistant && (
              <button
                className="btn small"
                onClick={() => askAssistant('Which target companies have I not applied to, and what is open at them right now?')}
              >
                Ask
              </button>
            )
          }
        >
          <TargetGaps companies={companies} />
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="Company board"
          sub={`${visible.length} of ${companies.length} shown`}
          actions={
            <div style={{ display: 'flex', gap: 8 }}>
              {companies.length === 0 && (
                <button
                  className="btn"
                  onClick={async () => {
                    await api.companies.seed()
                    reload()
                  }}
                >
                  Load curated list
                </button>
              )}
              <button className="btn primary" onClick={() => setAdding((v) => !v)}>
                {adding ? 'Cancel' : 'Add company'}
              </button>
            </div>
          }
        >
          {adding && (
            <CompanyForm
              meta={meta}
              onSave={async (body) => {
                await api.companies.create(body)
                setAdding(false)
                reload()
              }}
            />
          )}

          <div className="toolbar">
            <input
              placeholder="Search name, stack or city…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">Any status</option>
              <option value="applied">Applied</option>
              {(meta.company_statuses ?? []).map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="all">Any type</option>
              {(meta.company_types ?? []).map((c) => (
                <option key={c} value={c}>
                  {label(c)}
                </option>
              ))}
            </select>
            <select value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="all">Any tier</option>
              {(meta.company_tiers ?? []).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          {visible.length === 0 ? (
            <Empty>
              {companies.length === 0
                ? 'The board is empty. Load the curated list, or ask the assistant to add a company.'
                : 'No companies match those filters.'}
            </Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Tier</th>
                  <th>Status</th>
                  <th className="num">Want</th>
                  <th className="num">Sent</th>
                  <th>Board</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => (
                  <CompanyRow
                    key={c.id}
                    company={c}
                    meta={meta}
                    open={expanded === c.id}
                    onToggle={() => setExpanded(expanded === c.id ? null : c.id)}
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

function TargetGaps({ companies }) {
  const gaps = companies
    .filter((c) => c.status === 'target' && !c.applications && !c.leads)
    .sort((a, b) => (b.interest ?? 0) - (a.interest ?? 0))
    .slice(0, 8)

  // Three different nothings, and conflating them reads as a false all-clear:
  // an empty board, a board with nothing flagged, and targets all actioned.
  if (!companies.length) {
    return <p className="muted small">Nothing on the board yet.</p>
  }
  if (!companies.some((c) => c.status === 'target')) {
    return (
      <p className="muted small">
        Nothing flagged as a target yet. Set a few to <em>target</em> and this tracks what you
        haven&apos;t acted on.
      </p>
    )
  }
  if (!gaps.length) {
    return <p className="muted small">No unactioned targets — everything you flagged has something sent.</p>
  }
  return (
    <div className="rows">
      {gaps.map((c) => (
        <div key={c.id} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
          <span style={{ flex: 1 }}>{c.name}</span>
          <span className="row-value small muted">
            {c.interest ? `want ${c.interest}/5` : '—'}
            {c.discovery.last_checked ? ` · checked ${c.discovery.last_checked}` : ' · never checked'}
          </span>
        </div>
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------
// role discovery
// --------------------------------------------------------------------------

function Discovery({ companies, meta, reload }) {
  const [keywords, setKeywords] = useState(DEFAULT_KEYWORDS)
  const [scope, setScope] = useState('all')
  const [maxAge, setMaxAge] = useState('')
  const [includeRemote, setIncludeRemote] = useState(false)
  const [levels, setLevels] = useState({ intern: false, entry: true, mid: true, senior: false })
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [tracked, setTracked] = useState({})

  const wired = companies.filter((c) => c.ats_provider !== 'none')
  const wiredTargets = wired.filter((c) => c.status === 'target')

  const run = async () => {
    setRunning(true)
    setError(null)
    setTracked({})
    try {
      const ids =
        scope === 'targets' ? wiredTargets.map((c) => c.id) : scope === 'all' ? null : [scope]
      setResult(
        await api.discover.search({
          company_ids: ids,
          keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean),
          // The backend takes levels to exclude; the UI asks which to include.
          exclude_seniority: Object.entries(levels)
            .filter(([, on]) => !on)
            .map(([lvl]) => lvl),
          max_age_days: maxAge ? Number(maxAge) : null,
          include_remote: includeRemote,
          limit: 60,
        }),
      )
    } catch (err) {
      setError(String(err))
    } finally {
      setRunning(false)
      reload()
    }
  }

  const totals = result?.totals
  const errors = (result?.checked ?? []).filter((c) => c.error)

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title="Find roles"
        sub={
          wired.length
            ? `Reads the live job boards of ${wired.length} companies and hides anything you already track`
            : 'No company on the board has a searchable job board yet'
        }
        actions={
          <button className="btn primary" onClick={run} disabled={running || !wired.length}>
            {running ? 'Searching…' : 'Search boards'}
          </button>
        }
      >
        <div className="field-row">
          <Field label="Keywords (any match)">
            <input value={keywords} onChange={(e) => setKeywords(e.target.value)} />
          </Field>
          <Field label="Where">
            <select value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="all">All {wired.length} wired boards</option>
              <option value="targets">My targets only ({wiredTargets.length})</option>
              {wired.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Posted within">
            <select value={maxAge} onChange={(e) => setMaxAge(e.target.value)}>
              <option value="">Any time</option>
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
              <option value="30">Last 30 days</option>
              <option value="90">Last 90 days</option>
            </select>
          </Field>
        </div>

        <div className="field-row" style={{ alignItems: 'center' }}>
          <Field label="Levels to include">
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', paddingTop: 4 }}>
              {['intern', 'entry', 'mid', 'senior'].map((lvl) => (
                <label key={lvl} className="small" style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={levels[lvl]}
                    onChange={(e) => setLevels({ ...levels, [lvl]: e.target.checked })}
                    style={{ width: 'auto' }}
                  />
                  {lvl}
                </label>
              ))}
              <label className="small" style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                <input
                  type="checkbox"
                  checked={includeRemote}
                  onChange={(e) => setIncludeRemote(e.target.checked)}
                  style={{ width: 'auto' }}
                />
                include remote
              </label>
            </div>
          </Field>
        </div>

        <p className="small muted" style={{ marginTop: 4 }}>
          Level is inferred from the job title, so it is a filter and not a promise.
        </p>

        {error && (
          <p className="small" style={{ color: 'var(--critical)' }}>
            {error}
          </p>
        )}

        {totals && (
          <p className="small muted" style={{ marginTop: 10 }}>
            Checked {totals.companies_checked} board{totals.companies_checked === 1 ? '' : 's'} ·{' '}
            {totals.roles_seen} roles listed · {totals.after_filters} matched your filters ·{' '}
            {totals.already_tracked} already tracked · <strong>{totals.new} new</strong>
            {errors.length > 0 && ` · ${errors.length} board${errors.length === 1 ? '' : 's'} failed`}
          </p>
        )}

        {errors.length > 0 && (
          <p className="small muted">
            Failed: {errors.map((e) => `${e.company} (${e.error})`).join(', ')}
          </p>
        )}

        {result?.note && <p className="small muted">{result.note}</p>}

        {result && result.roles.length === 0 && !result.note && (
          <Empty>Nothing new matched. Widen the keywords or the date range.</Empty>
        )}

        {result && result.roles.length > 0 && (
          <table className="table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>Role</th>
                <th>Company</th>
                <th>Level</th>
                <th>Posted</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {result.roles.map((role) => (
                <tr key={role.url}>
                  <td>
                    <div className="row-main">
                      <a href={role.url} target="_blank" rel="noreferrer">
                        {role.title}
                      </a>
                    </div>
                    <div className="row-sub">{role.location || 'Location not stated'}</div>
                  </td>
                  <td>{role.company}</td>
                  <td>
                    <Pill tone="">{role.seniority}</Pill>
                  </td>
                  <td className="small muted">{role.posted ?? '—'}</td>
                  <td className="num">
                    <button
                      className="btn small"
                      disabled={tracked[role.url]}
                      onClick={async () => {
                        await api.discover.promote(role)
                        setTracked((t) => ({ ...t, [role.url]: true }))
                        reload()
                      }}
                    >
                      {tracked[role.url] ? 'Tracked' : 'Track'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

// --------------------------------------------------------------------------
// board rows
// --------------------------------------------------------------------------

function CompanyRow({ company, meta, open, onToggle, reload }) {
  const [busy, setBusy] = useState(false)

  const patch = async (body) => {
    setBusy(true)
    try {
      await api.companies.update(company.id, body)
      reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">{company.name}</div>
          <div className="row-sub">
            {company.locations.join(', ') || 'Location unknown'}
            {company.focus.length > 0 && ` · ${company.focus.join(', ')}`}
          </div>
        </td>
        <td>
          <Pill tone="">{company.tier ?? '—'}</Pill>
        </td>
        <td>
          {company.applications > 0 ? (
            <Pill tone="blue">applied</Pill>
          ) : (
            <select
              value={company.status}
              disabled={busy}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => patch({ status: e.target.value })}
              style={{ width: 'auto', padding: '4px 6px', fontSize: 12 }}
            >
              {(meta.company_statuses ?? []).map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          )}
        </td>
        <td className="num">
          <select
            value={company.interest ?? ''}
            disabled={busy}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => patch({ interest: e.target.value ? Number(e.target.value) : null })}
            style={{ width: 'auto', padding: '4px 6px', fontSize: 12 }}
          >
            <option value="">—</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </td>
        <td className="num">{company.applications || (company.leads ? `${company.leads} lead` : '—')}</td>
        <td>
          {company.ats_provider === 'none' ? (
            <span className="muted small">—</span>
          ) : (
            <span className="tag">{company.ats_provider}</span>
          )}
        </td>
      </tr>

      {open && (
        <tr className="detail">
          <td colSpan={6}>
            <div className="detail-inner">
              <div>
                <h4>What they do</h4>
                <p className="small">{company.org_summary || <span className="muted">No summary yet.</span>}</p>
                <div className="small" style={{ marginTop: 10 }}>
                  <div className="muted" style={{ marginBottom: 3 }}>
                    Stack
                  </div>
                  <Tags items={company.tech_stack} />
                </div>
                <p className="small muted" style={{ marginTop: 10 }}>
                  {company.category} · {company.tier ?? 'untiered'}
                  {company.hq && <> · HQ {company.hq}</>}
                </p>
                {company.careers_url && (
                  <p className="small" style={{ marginTop: 8 }}>
                    <a href={company.careers_url} target="_blank" rel="noreferrer">
                      Careers page ↗
                    </a>
                  </p>
                )}
              </div>

              <div>
                <h4>Job board</h4>
                {company.ats_provider === 'none' ? (
                  <p className="small muted">
                    No machine-readable board, so discovery can&apos;t search this one. The
                    assistant can look it up on the web instead. If you find their board token,
                    set it below and it joins the automated search.
                  </p>
                ) : (
                  <p className="small">
                    Wired to <span className="tag">{company.ats_provider}</span>
                    <br />
                    <span className="muted">
                      {company.discovery.last_checked
                        ? `Last checked ${company.discovery.last_checked}, ${company.discovery.last_count ?? 0} roles listed`
                        : 'Never checked'}
                      {company.discovery.last_error && ` — ${company.discovery.last_error}`}
                    </span>
                  </p>
                )}
                <div className="field-row" style={{ marginTop: 10 }}>
                  <Field label="Provider">
                    <select
                      value={company.ats_provider}
                      onChange={(e) => patch({ ats_provider: e.target.value })}
                    >
                      {(meta.ats_providers ?? ['none']).map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Board token">
                    <input
                      defaultValue={company.ats_token ?? ''}
                      placeholder="e.g. razorpaysoftwareprivatelimited"
                      onBlur={(e) => {
                        if (e.target.value !== (company.ats_token ?? '')) {
                          patch({ ats_token: e.target.value || null })
                        }
                      }}
                    />
                  </Field>
                </div>
              </div>

              <div>
                <h4>Notes</h4>
                <textarea
                  defaultValue={company.notes}
                  placeholder="Referrals, interview format, what they asked…"
                  onBlur={(e) => {
                    if (e.target.value !== company.notes) patch({ notes: e.target.value })
                  }}
                />
                <p className="small muted" style={{ marginTop: 10 }}>
                  {company.applications} application{company.applications === 1 ? '' : 's'} ·{' '}
                  {company.leads} lead{company.leads === 1 ? '' : 's'}
                  {company.application_statuses.length > 0 && (
                    <> · {company.application_statuses.join(', ')}</>
                  )}
                </p>
                <button
                  className="btn small ghost"
                  style={{ marginTop: 10, color: 'var(--critical)' }}
                  onClick={async () => {
                    if (confirm(`Remove ${company.name} from the board?`)) {
                      await api.companies.remove(company.id)
                      reload()
                    }
                  }}
                >
                  Remove from board
                </button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function CompanyForm({ meta, onSave }) {
  const [form, setForm] = useState({
    name: '',
    category: 'product',
    tier: 'growth',
    status: 'target',
    locations: '',
    careers_url: '',
    ats_provider: 'none',
    ats_token: '',
    tech_stack: '',
    interest: 4,
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const listOf = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)

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
        <Field label="Name">
          <input value={form.name} onChange={set('name')} placeholder="Company name" />
        </Field>
        <Field label="Type">
          <select value={form.category} onChange={set('category')}>
            {(meta.company_types ?? []).map((c) => (
              <option key={c} value={c}>
                {label(c)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Tier">
          <select value={form.tier} onChange={set('tier')}>
            {(meta.company_tiers ?? []).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select value={form.status} onChange={set('status')}>
            {(meta.company_statuses ?? []).map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Want (1-5)">
          <select value={form.interest} onChange={set('interest')}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="field-row">
        <Field label="Locations">
          <input value={form.locations} onChange={set('locations')} placeholder="Bengaluru, Pune" />
        </Field>
        <Field label="Careers URL">
          <input value={form.careers_url} onChange={set('careers_url')} placeholder="https://…" />
        </Field>
        <Field label="Stack">
          <input value={form.tech_stack} onChange={set('tech_stack')} placeholder="Java, Kafka" />
        </Field>
      </div>
      <div className="field-row">
        <Field label="Board provider">
          <select value={form.ats_provider} onChange={set('ats_provider')}>
            {(meta.ats_providers ?? ['none']).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Board token (only if you're sure)">
          <input value={form.ats_token} onChange={set('ats_token')} placeholder="leave blank if unknown" />
        </Field>
      </div>
      <button
        className="btn primary"
        onClick={() => {
          if (!form.name.trim()) return
          onSave({
            ...form,
            interest: Number(form.interest),
            locations: listOf(form.locations),
            tech_stack: listOf(form.tech_stack),
            careers_url: form.careers_url || null,
            ats_token: form.ats_token || null,
          })
        }}
      >
        Add to board
      </button>
    </div>
  )
}
