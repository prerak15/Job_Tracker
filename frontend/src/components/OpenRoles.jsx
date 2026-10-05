import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { CompanyForm } from './Companies'
import { Card, Empty, Field, Pill, Tile, label, plural } from './ui'

// One list over both ways roles are found: the public job boards (read live)
// and the careers pages (read by the scraper, last result per company). The
// filters are the same file the scraper's workbook uses, so what this tab shows
// and what the Excel export lists can't disagree.

const PAGE = 100
const LEVELS = ['intern', 'entry', 'mid', 'senior']

// Kept across tab switches for the life of the page: checking 80+ boards takes
// seconds, and switching back to this tab shouldn't pay that again.
let lastResult = null

export default function OpenRoles({ companies, meta, reload, askAssistant }) {
  const [result, setResult] = useState(lastResult)
  const [loading, setLoading] = useState(!lastResult)
  const [error, setError] = useState(null)

  const load = useCallback(async (refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.roles.list(refresh)
      lastResult = data
      setResult(data)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!lastResult) load()
  }, [load])

  const totals = result?.totals ?? {}

  return (
    <>
      <div className="tiles">
        <Tile label="Open roles" value={result ? totals.roles : '…'} note={`at ${totals.companies ?? 0} companies, not yet tracked`} />
        <Tile label="From job boards" value={totals.from_boards ?? '—'} note={`${totals.boards_checked ?? 0} boards read live`} />
        <Tile
          label="From careers pages"
          value={totals.from_pages ?? '—'}
          note={result?.pages_read_on ? `last read ${result.pages_read_on}` : 'never read'}
        />
        <Tile label="Already tracked" value={totals.already_tracked ?? '—'} note="hidden here" />
        <Tile
          label="Pages failing"
          value={totals.pages_failing ?? '—'}
          note={`of ${totals.pages_read ?? 0} careers pages`}
        />
      </div>

      {result && <Filters filters={result.filters} onSaved={() => load()} />}

      <RoleList
        result={result}
        loading={loading}
        error={error}
        onRefresh={() => load(true)}
        reloadDashboard={reload}
        meta={meta}
      />

      <ScrapeRunner onFinished={() => load()} initial={result?.scrape} />

      <FindCompanies companies={companies} meta={meta} reload={reload} askAssistant={askAssistant} />
    </>
  )
}

// --------------------------------------------------------------------------
// filters — saved to data/role-filters.json
// --------------------------------------------------------------------------

function Filters({ filters, onSaved }) {
  const [keywords, setKeywords] = useState(filters.keywords.join(', '))
  const [expOn, setExpOn] = useState(Boolean(filters.experience))
  const [expMin, setExpMin] = useState(filters.experience?.min ?? 0)
  const [expMax, setExpMax] = useState(filters.experience?.max ?? 3)
  const [required, setRequired] = useState(Boolean(filters.experience?.required))
  const [levels, setLevels] = useState(
    Object.fromEntries(LEVELS.map((l) => [l, !filters.exclude_seniority.includes(l)])),
  )
  const [maxAge, setMaxAge] = useState(filters.max_age_days ?? '')
  const [remote, setRemote] = useState(filters.include_remote)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.roles.saveFilters({
        keywords: keywords.split(',').map((k) => k.trim()).filter(Boolean),
        experience: expOn ? { min: Number(expMin), max: Number(expMax), required } : null,
        exclude_seniority: LEVELS.filter((l) => !levels[l]),
        max_age_days: maxAge === '' ? null : Number(maxAge),
        include_remote: remote,
      })
      onSaved()
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title="What you're looking for"
        sub="Saved for this tab and for the scraper's Excel export alike"
        actions={
          <button className="btn primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save and apply'}
          </button>
        }
      >
        <Field label="Role keywords (any match, on the title or team)">
          <textarea rows={2} value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        </Field>
        <p className="small muted" style={{ marginTop: -4 }}>
          Covers software engineer and developer, ML engineer and AI engineer titles.{' '}
          <button
            className="btn small ghost"
            onClick={() => setKeywords(filters.default_keywords.join(', '))}
          >
            Reset to defaults
          </button>
        </p>

        <div className="field-row" style={{ alignItems: 'end' }}>
          <Field label="Experience (years)">
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label className="small" style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                <input type="checkbox" checked={expOn} onChange={(e) => setExpOn(e.target.checked)} style={{ width: 'auto' }} />
                filter
              </label>
              <input
                type="number" min={0} max={30} step={1} value={expMin} disabled={!expOn}
                onChange={(e) => setExpMin(e.target.value)} style={{ width: 70 }} aria-label="Minimum years"
              />
              <span className="muted">to</span>
              <input
                type="number" min={0} max={30} step={1} value={expMax} disabled={!expOn}
                onChange={(e) => setExpMax(e.target.value)} style={{ width: 70 }} aria-label="Maximum years"
              />
            </div>
          </Field>
          <Field label="Postings that don't say">
            <select value={required ? 'hide' : 'keep'} disabled={!expOn} onChange={(e) => setRequired(e.target.value === 'hide')}>
              <option value="keep">Keep them (most pages never state it)</option>
              <option value="hide">Hide them</option>
            </select>
          </Field>
          <Field label="Posted within">
            <select value={maxAge} onChange={(e) => setMaxAge(e.target.value)}>
              <option value="">Any time</option>
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
              <option value="30">Last 30 days</option>
              <option value="60">Last 60 days</option>
            </select>
          </Field>
        </div>

        <Field label="Levels to include (read from the title)">
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', paddingTop: 2 }}>
            {LEVELS.map((lvl) => (
              <label key={lvl} className="small" style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                <input
                  type="checkbox" checked={levels[lvl]} style={{ width: 'auto' }}
                  onChange={(e) => setLevels({ ...levels, [lvl]: e.target.checked })}
                />
                {lvl}
              </label>
            ))}
            <label className="small" style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
              <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} style={{ width: 'auto' }} />
              include remote
            </label>
          </div>
        </Field>
        <p className="small muted">
          A range matches by overlap: with 0–3, a &ldquo;2–5 years&rdquo; posting stays and a
          &ldquo;6–9 years&rdquo; one goes. Years come from the board&apos;s own field, the title, or
          the job description.
        </p>
        {error && <p className="small" style={{ color: 'var(--critical)' }}>{error}</p>}
      </Card>
    </div>
  )
}

// --------------------------------------------------------------------------
// the list
// --------------------------------------------------------------------------

function RoleList({ result, loading, error, onRefresh, reloadDashboard, meta }) {
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('all')
  const [tier, setTier] = useState('all')
  const [shown, setShown] = useState(PAGE)
  const [tracked, setTracked] = useState({})

  const roles = result?.roles ?? []
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return roles
      .filter((r) => source === 'all' || r.source === source)
      .filter((r) => tier === 'all' || r.tier === tier)
      .filter(
        (r) =>
          !needle ||
          r.title.toLowerCase().includes(needle) ||
          r.company.toLowerCase().includes(needle) ||
          (r.location || '').toLowerCase().includes(needle),
      )
  }, [roles, search, source, tier])

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title="Open roles"
        sub={
          result
            ? `${visible.length} of ${roles.length} shown · job boards read live, careers pages as of their last read`
            : 'Reading job boards…'
        }
        actions={
          <button className="btn" onClick={onRefresh} disabled={loading}>
            {loading ? 'Checking…' : 'Re-check job boards'}
          </button>
        }
      >
        <div className="toolbar">
          <input placeholder="Search title, company or city…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="all">Both sources</option>
            <option value="job board">Job boards</option>
            <option value="careers page">Careers pages</option>
          </select>
          <select value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="all">Any tier</option>
            {(meta?.company_tiers ?? []).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        {error && <p className="small" style={{ color: 'var(--critical)' }}>{error}</p>}
        {result?.board_errors?.length > 0 && (
          <p className="small muted">
            {plural(result.board_errors.length, 'board')} failed:{' '}
            {result.board_errors.map((e) => `${e.company} (${e.error})`).join(', ')}
          </p>
        )}

        {loading && !result ? (
          <p className="muted">Reading every wired job board — this takes a few seconds the first time.</p>
        ) : visible.length === 0 ? (
          <Empty>
            {roles.length
              ? 'Nothing matches that search.'
              : 'No untracked roles match your filters. Widen them, or refresh the careers pages below.'}
          </Empty>
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Company</th>
                  <th>Experience</th>
                  <th>Level</th>
                  <th>Posted</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.slice(0, shown).map((role) => (
                  <tr key={role.url}>
                    <td>
                      <div className="row-main">
                        <a href={role.url} target="_blank" rel="noreferrer">{role.title}</a>
                      </div>
                      <div className="row-sub">
                        {role.location || 'Location not stated'} · {role.source}
                      </div>
                    </td>
                    <td>
                      <div className="row-main">{role.company}</div>
                      <div className="row-sub">{role.tier ?? '—'}</div>
                    </td>
                    <td className="small">{role.experience || <span className="muted">not stated</span>}</td>
                    <td><Pill tone="">{role.seniority}</Pill></td>
                    <td className="small muted">{role.posted ?? '—'}</td>
                    <td className="num">
                      <button
                        className="btn small"
                        disabled={tracked[role.url]}
                        onClick={async () => {
                          await api.discover.promote(role)
                          setTracked((t) => ({ ...t, [role.url]: true }))
                          reloadDashboard()
                        }}
                      >
                        {tracked[role.url] ? 'Tracked' : 'Track'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visible.length > shown && (
              <button className="btn small" style={{ marginTop: 10 }} onClick={() => setShown(shown + PAGE)}>
                Show {Math.min(PAGE, visible.length - shown)} more
              </button>
            )}
          </>
        )}
        <p className="small muted" style={{ marginTop: 10 }}>
          Level and experience are read from the posting, so they are filters and not promises.
          Track saves a role to Applications as &ldquo;yet to apply&rdquo;.
        </p>
      </Card>
    </div>
  )
}

// --------------------------------------------------------------------------
// running the careers-page scraper
// --------------------------------------------------------------------------

const SCOPE_LABELS = {
  startups: 'Startups (growth + early)',
  targets: 'My targets',
  top: 'Top tier (faang + tier1)',
  mid: 'Mid tier (tier2)',
  all: 'Every careers page (slow)',
}

function ScrapeRunner({ onFinished, initial }) {
  const [status, setStatus] = useState(initial ?? null)
  const [scope, setScope] = useState('startups')
  const [error, setError] = useState(null)
  const wasRunning = useRef(Boolean(initial?.running))

  const poll = useCallback(async () => {
    try {
      const next = await api.roles.scrapeStatus()
      setStatus(next)
      if (wasRunning.current && !next.running) onFinished()
      wasRunning.current = next.running
    } catch (err) {
      setError(String(err))
    }
  }, [onFinished])

  useEffect(() => {
    poll()
  }, [poll])

  useEffect(() => {
    if (!status?.running) return undefined
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [status?.running, poll])

  const start = async () => {
    setError(null)
    try {
      const next = await api.roles.startScrape({ scope })
      wasRunning.current = true
      setStatus(next)
    } catch (err) {
      setError(String(err))
    }
  }

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title="Refresh careers pages"
        sub="Companies without a public job board are read in a headless browser. A run takes a few minutes and costs no tokens."
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <select value={scope} onChange={(e) => setScope(e.target.value)} disabled={status?.running} style={{ width: 'auto' }}>
              {(status?.scopes ?? Object.keys(SCOPE_LABELS)).map((s) => (
                <option key={s} value={s}>{SCOPE_LABELS[s] ?? s}</option>
              ))}
            </select>
            <button className="btn primary" onClick={start} disabled={status?.running}>
              {status?.running ? 'Running…' : 'Run'}
            </button>
          </div>
        }
      >
        {error && <p className="small" style={{ color: 'var(--critical)' }}>{error}</p>}
        {status?.running && (
          <p className="small">Reading {status.scope}… the list above updates when it finishes.</p>
        )}
        {!status?.running && status?.exit_code !== null && status?.exit_code !== undefined && (
          <p className="small muted">
            Last run ({status.scope}) {status.exit_code === 0 ? 'finished' : `exited with code ${status.exit_code}`}.
            Sites it couldn&apos;t read are listed with the reason; the help list is{' '}
            <code>backend/scrape.py --needs-help</code>.
          </p>
        )}
        {status?.log_tail?.length > 0 && (
          <pre className="small" style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: 'var(--tint-neutral)', padding: 10, borderRadius: 'var(--radius-sm)' }}>
            {status.log_tail.join('\n')}
          </pre>
        )}
      </Card>
    </div>
  )
}

// --------------------------------------------------------------------------
// finding and adding companies
// --------------------------------------------------------------------------

function FindCompanies({ companies, meta, reload, askAssistant }) {
  const [suggestions, setSuggestions] = useState([])
  const [tier, setTier] = useState('all')
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)
  const [like, setLike] = useState('')
  const [busy, setBusy] = useState({})

  const loadSuggestions = useCallback(async () => {
    setSuggestions(await api.companies.suggestions())
  }, [])

  useEffect(() => {
    loadSuggestions()
  }, [loadSuggestions, companies.length])

  const visible = suggestions
    .filter((s) => tier === 'all' || s.tier === tier)
    .filter((s) => category === 'all' || s.category === category)
    .filter((s) => {
      const needle = search.trim().toLowerCase()
      return !needle || s.name.toLowerCase().includes(needle) || s.locations.some((l) => l.toLowerCase().includes(needle))
    })

  const add = async (names) => {
    setBusy((b) => ({ ...b, ...Object.fromEntries(names.map((n) => [n, true])) }))
    try {
      await api.companies.addSuggestions(names)
      await loadSuggestions()
      reload()
    } finally {
      setBusy({})
    }
  }

  const ask = () => {
    const seed = like.trim() || 'Tredence, ThoughtSpot and Rippling'
    askAssistant(
      `Find 10 more companies like ${seed} that hire early-career software, ML or AI engineers in India ` +
        `(Bengaluru first). Skip any already on my company board. For each, find the real careers page ` +
        `(and a Greenhouse/Lever/Ashby board token only if you can verify it lists that company), then add ` +
        `it to my board with a one-line summary, tier and category.`,
    )
  }

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title="Find more companies"
        sub={`${companies.length} on your board · ${suggestions.length} curated suggestions not added yet`}
        actions={
          <button className="btn" onClick={() => setAdding((v) => !v)}>
            {adding ? 'Cancel' : 'Add one by hand'}
          </button>
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

        {askAssistant && (
          <div className="field-row" style={{ alignItems: 'end' }}>
            <Field label="Ask the assistant for companies like…">
              <input
                value={like}
                onChange={(e) => setLike(e.target.value)}
                placeholder="e.g. Tredence, ThoughtSpot, Rippling"
                onKeyDown={(e) => e.key === 'Enter' && ask()}
              />
            </Field>
            <div className="field">
              <button className="btn primary" onClick={ask}>Ask</button>
            </div>
          </div>
        )}

        <div className="toolbar">
          <input placeholder="Search name or city…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select value={tier} onChange={(e) => setTier(e.target.value)}>
            <option value="all">Any tier</option>
            {(meta?.company_tiers ?? []).map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">Any type</option>
            {(meta?.company_types ?? []).map((c) => (
              <option key={c} value={c}>{label(c)}</option>
            ))}
          </select>
          <span className="spacer" />
          {visible.length > 1 && (
            <button className="btn small" onClick={() => add(visible.map((s) => s.name))}>
              Add all {visible.length} shown
            </button>
          )}
        </div>

        {visible.length === 0 ? (
          <Empty>
            {suggestions.length
              ? 'No suggestions match those filters.'
              : 'Every curated company is already on your board. Ask the assistant for more.'}
          </Empty>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Tier</th>
                <th>Where</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.name}>
                  <td>
                    <div className="row-main">
                      {s.careers_url ? (
                        <a href={s.careers_url} target="_blank" rel="noreferrer">{s.name}</a>
                      ) : (
                        s.name
                      )}
                    </div>
                    <div className="row-sub">{s.org_summary}</div>
                  </td>
                  <td>
                    <Pill tone="">{s.tier}</Pill>
                    <div className="row-sub">{label(s.category)}</div>
                  </td>
                  <td className="small">{s.locations.join(', ')}</td>
                  <td className="num">
                    <button className="btn small" disabled={busy[s.name]} onClick={() => add([s.name])}>
                      {busy[s.name] ? 'Adding…' : 'Add'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="small muted" style={{ marginTop: 10 }}>
          Added companies are read on the next careers-page run (or live, if they have a public job
          board). Remove any from the Companies tab.
        </p>
      </Card>
    </div>
  )
}
