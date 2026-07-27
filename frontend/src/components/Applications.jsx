import { useMemo, useState } from 'react'
import { api } from '../api'
import { BarRows, Card, Empty, Field, Pill, Tile, ago, label, pct, plural } from './ui'

const BLANK = {
  job_title: '',
  organisation: '',
  status: 'applied',
  date_job_posted: '',
  company_type: '',
  industry: '',
  source: '',
  location: '',
  salary_range: '',
  url: '',
  org_summary: '',
  job_description: '',
  referred_by: '',
  notes: '',
}

export default function Applications({ jobs, stats, followups, meta, resumes, reload }) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [expanded, setExpanded] = useState(null)
  const [adding, setAdding] = useState(false)

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return jobs
      .filter((j) => statusFilter === 'all' || j.status === statusFilter)
      .filter(
        (j) =>
          !needle ||
          j.organisation.toLowerCase().includes(needle) ||
          j.job_title.toLowerCase().includes(needle),
      )
      .sort((a, b) => (b.latest_update_date || '').localeCompare(a.latest_update_date || ''))
  }, [jobs, search, statusFilter])

  const statusRows = meta.statuses
    .map((s) => ({
      label: label(s),
      value: stats.by_status?.[s] ?? 0,
      share: stats.status_percentages?.[s] ?? 0,
    }))
    .filter((r) => r.value > 0)

  const sourceRows = Object.entries(stats.by_source ?? {}).map(([k, v]) => ({
    label: label(k),
    value: v.applications,
    rate: v.response_rate,
  }))

  const typeRows = Object.entries(stats.by_company_type ?? {}).map(([k, v]) => ({
    label: label(k),
    value: v.applications,
    rate: v.response_rate,
  }))

  return (
    <>
      <div className="tiles">
        <Tile label="Applications" value={stats.applied_total ?? 0} note={`${stats.total ?? 0} tracked incl. saved`} />
        <Tile label="Active pipeline" value={stats.active ?? 0} note="applied or interviewing" />
        <Tile label="Response rate" value={pct(stats.response_rate)} note="heard back at all" />
        <Tile label="Interview rate" value={pct(stats.interview_rate)} note="reached a round" />
        <Tile label="Offer rate" value={pct(stats.offer_rate)} note={plural(stats.by_status?.offer ?? 0, 'offer')} />
        <Tile label="Per week" value={stats.applications_per_week ?? 0} note="last 4 weeks" />
      </div>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))' }}>
        <Card title="Pipeline" sub="Where every application currently sits">
          <BarRows
            items={statusRows}
            empty="No applications yet."
            formatValue={(i) => `${i.value} · ${i.share}%`}
          />
        </Card>

        <Card title="Follow-ups due" sub="Active applications that have gone quiet">
          {followups.length === 0 ? (
            <p className="muted small">Nothing is overdue. Everything is either recent or moving.</p>
          ) : (
            <div className="rows">
              {followups.map((f) => (
                <div
                  key={f.id}
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
                      {f.organisation}
                    </div>
                    <div className="row-sub">
                      No activity for {ago(f.days_since_activity)}
                      {f.contacts?.length > 0 && ` · ${f.contacts[0].name}`}
                      {f.follow_ups_sent > 0 && ` · ${plural(f.follow_ups_sent, 'follow-up')} sent`}
                    </div>
                  </div>
                  <button
                    className="btn small"
                    onClick={async () => {
                      await api.jobs.followup(f.id, { note: 'Followed up' })
                      reload()
                    }}
                  >
                    Log follow-up
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="By source" sub="Volume, and how often each channel replies">
          <BarRows
            items={sourceRows}
            empty="No source recorded yet."
            formatValue={(i) => `${i.value} · ${i.rate}% reply`}
          />
        </Card>

        <Card title="By company type" sub="Startup vs product vs service and how they respond">
          <BarRows
            items={typeRows}
            empty="No company type recorded yet."
            formatValue={(i) => `${i.value} · ${i.rate}% reply`}
          />
        </Card>
      </div>

      <div style={{ marginTop: 16 }}>
        <Card
          title="Applications"
          sub={`${visible.length} shown`}
          actions={
            <button className="btn primary" onClick={() => setAdding((v) => !v)}>
              {adding ? 'Cancel' : 'Add application'}
            </button>
          }
        >
          {adding && (
            <JobForm
              meta={meta}
              onSave={async (body) => {
                await api.jobs.create(body)
                setAdding(false)
                reload()
              }}
            />
          )}

          <div className="toolbar">
            <input
              placeholder="Search title or organisation…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">All statuses</option>
              {meta.statuses.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
          </div>

          {visible.length === 0 ? (
            <Empty>
              No applications match. Paste a job posting into the chat and it will be added for you.
            </Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Latest update</th>
                  <th className="num">Rounds</th>
                  <th className="num">Follow-ups</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    meta={meta}
                    resumes={resumes}
                    open={expanded === job.id}
                    onToggle={() => setExpanded(expanded === job.id ? null : job.id)}
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

function JobRow({ job, meta, resumes, open, onToggle, reload }) {
  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">{job.job_title || 'Untitled role'}</div>
          <div className="row-sub">
            {job.organisation}
            {job.company_type && ` · ${label(job.company_type)}`}
            {job.location && ` · ${job.location}`}
          </div>
        </td>
        <td>
          <select
            value={job.status}
            onClick={(e) => e.stopPropagation()}
            onChange={async (e) => {
              await api.jobs.update(job.id, {
                status: e.target.value,
                latest_update: `Status set to ${label(e.target.value)}`,
              })
              reload()
            }}
            style={{ width: 'auto', padding: '4px 6px', fontSize: 12 }}
          >
            {meta.statuses.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </td>
        <td style={{ maxWidth: 320 }}>
          <div className="small">{job.latest_update || '—'}</div>
          <div className="row-sub">{job.latest_update_date}</div>
        </td>
        <td className="num">{job.rounds.length}</td>
        <td className="num">{job.follow_ups_sent.length}</td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={5}>
            <JobDetail job={job} meta={meta} resumes={resumes} reload={reload} />
          </td>
        </tr>
      )}
    </>
  )
}

function JobDetail({ job, meta, resumes, reload }) {
  const [round, setRound] = useState({ name: '', result: 'pending', feedback: '' })
  const [contact, setContact] = useState({ name: '', role: 'recruiter', email: '', is_referral: false })
  const [note, setNote] = useState('')

  return (
    <div className="detail-inner">
      <div>
        <h4>About</h4>
        {job.org_summary ? (
          <p className="small" style={{ marginTop: 0 }}>
            {job.org_summary}
          </p>
        ) : (
          <p className="muted small" style={{ marginTop: 0 }}>
            No summary yet — ask the assistant to look the company up.
          </p>
        )}
        <p className="small muted">
          {job.industry && <>Industry: {job.industry}<br /></>}
          {job.source && <>Source: {label(job.source)}<br /></>}
          {job.salary_range && <>Salary: {job.salary_range}<br /></>}
          {job.referred_by && <>Referred by: {job.referred_by}<br /></>}
          {job.date_job_posted && <>Posted: {job.date_job_posted}<br /></>}
          Created: {job.date_created}
        </p>
        {job.url && (
          <a className="small" href={job.url} target="_blank" rel="noreferrer">
            Open posting ↗
          </a>
        )}

        <h4 style={{ marginTop: 16 }}>Resume sent</h4>
        <select
          value={job.resume_id ?? ''}
          onChange={async (e) => {
            if (e.target.value) await api.resumes.link(e.target.value, job.id)
            else await api.jobs.update(job.id, { resume_id: null })
            reload()
          }}
        >
          <option value="">Not recorded</option>
          {resumes.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} {r.version_label && `(${r.version_label})`}
            </option>
          ))}
        </select>
      </div>

      <div>
        <h4>Rounds &amp; feedback</h4>
        {job.rounds.length === 0 && <p className="muted small">No rounds yet.</p>}
        {job.rounds.map((r) => (
          <div className="list-note" key={r.round}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
              <strong>
                Round {r.round}
                {r.name ? ` · ${r.name}` : ''}
              </strong>
              <Pill>{r.result}</Pill>
              <span className="when">{r.date}</span>
            </div>
            <textarea
              defaultValue={r.feedback}
              placeholder="What happened, what was hard…"
              onBlur={async (e) => {
                if (e.target.value !== r.feedback) {
                  await api.jobs.updateRound(job.id, r.round, { feedback: e.target.value })
                  reload()
                }
              }}
              style={{ minHeight: 54, fontSize: 12.5 }}
            />
          </div>
        ))}

        <div className="field-row" style={{ marginTop: 10 }}>
          <input
            placeholder="Round name"
            value={round.name}
            onChange={(e) => setRound({ ...round, name: e.target.value })}
          />
          <select
            value={round.result}
            onChange={(e) => setRound({ ...round, result: e.target.value })}
          >
            {meta.round_results.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
        </div>
        <textarea
          placeholder="Feedback"
          value={round.feedback}
          onChange={(e) => setRound({ ...round, feedback: e.target.value })}
          style={{ marginTop: 8, minHeight: 54 }}
        />
        <button
          className="btn small"
          style={{ marginTop: 8 }}
          onClick={async () => {
            if (!round.name && !round.feedback) return
            await api.jobs.addRound(job.id, round)
            setRound({ name: '', result: 'pending', feedback: '' })
            reload()
          }}
        >
          Add round
        </button>
      </div>

      <div>
        <h4>Contacts</h4>
        {job.contacts.length === 0 && <p className="muted small">No contacts yet.</p>}
        {job.contacts.map((c, i) => (
          <div className="list-note" key={i}>
            <strong>{c.name}</strong> <span className="when">{label(c.role)}</span>
            {c.is_referral && <span className="tag" style={{ marginLeft: 6 }}>referral</span>}
            {c.email && <div className="when">{c.email}</div>}
            {c.linkedin && <div className="when">{c.linkedin}</div>}
          </div>
        ))}
        <div className="field-row" style={{ marginTop: 10 }}>
          <input
            placeholder="Name"
            value={contact.name}
            onChange={(e) => setContact({ ...contact, name: e.target.value })}
          />
          <select
            value={contact.role}
            onChange={(e) => setContact({ ...contact, role: e.target.value })}
          >
            {meta.contact_roles.map((r) => (
              <option key={r} value={r}>
                {label(r)}
              </option>
            ))}
          </select>
        </div>
        <input
          placeholder="Email or LinkedIn"
          value={contact.email}
          onChange={(e) => setContact({ ...contact, email: e.target.value })}
          style={{ marginTop: 8 }}
        />
        <label className="small" style={{ display: 'block', margin: '8px 0' }}>
          <input
            type="checkbox"
            checked={contact.is_referral}
            onChange={(e) => setContact({ ...contact, is_referral: e.target.checked })}
            style={{ width: 'auto', marginRight: 6 }}
          />
          Gave me a referral
        </label>
        <button
          className="btn small"
          onClick={async () => {
            if (!contact.name) return
            await api.jobs.addContact(job.id, contact)
            setContact({ name: '', role: 'recruiter', email: '', is_referral: false })
            reload()
          }}
        >
          Add contact
        </button>
      </div>

      <div>
        <h4>Follow-ups</h4>
        {job.follow_ups_sent.length === 0 && <p className="muted small">None sent.</p>}
        {job.follow_ups_sent.map((f, i) => (
          <div className="list-note" key={i}>
            <div className="when">{f.date}</div>
            {f.note || 'Follow-up sent'}
          </div>
        ))}
        <input
          placeholder="Follow-up note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          style={{ marginTop: 8 }}
        />
        <button
          className="btn small"
          style={{ marginTop: 8 }}
          onClick={async () => {
            await api.jobs.followup(job.id, { note })
            setNote('')
            reload()
          }}
        >
          Log follow-up
        </button>

        <h4 style={{ marginTop: 16 }}>Notes</h4>
        <textarea
          defaultValue={job.notes}
          onBlur={async (e) => {
            if (e.target.value !== job.notes) {
              await api.jobs.update(job.id, { notes: e.target.value })
              reload()
            }
          }}
        />
        <button
          className="btn small ghost"
          style={{ marginTop: 10, color: 'var(--critical)' }}
          onClick={async () => {
            if (confirm(`Delete the ${job.organisation} application? This cannot be undone.`)) {
              await api.jobs.remove(job.id)
              reload()
            }
          }}
        >
          Delete application
        </button>
      </div>
    </div>
  )
}

function JobForm({ meta, onSave }) {
  const [form, setForm] = useState(BLANK)
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
        <Field label="Job title">
          <input value={form.job_title} onChange={set('job_title')} />
        </Field>
        <Field label="Organisation">
          <input value={form.organisation} onChange={set('organisation')} />
        </Field>
        <Field label="Status">
          <select value={form.status} onChange={set('status')}>
            {meta.statuses.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="field-row">
        <Field label="Company type">
          <select value={form.company_type} onChange={set('company_type')}>
            <option value="">—</option>
            {meta.company_types.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Source">
          <select value={form.source} onChange={set('source')}>
            <option value="">—</option>
            {meta.sources.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Industry">
          <input value={form.industry} onChange={set('industry')} />
        </Field>
        <Field label="Location">
          <input value={form.location} onChange={set('location')} />
        </Field>
      </div>
      <div className="field-row">
        <Field label="Date posted">
          <input type="date" value={form.date_job_posted} onChange={set('date_job_posted')} />
        </Field>
        <Field label="Salary range">
          <input value={form.salary_range} onChange={set('salary_range')} />
        </Field>
        <Field label="Posting URL">
          <input value={form.url} onChange={set('url')} />
        </Field>
      </div>
      <Field label="Job description (used for resume tailoring)">
        <textarea value={form.job_description} onChange={set('job_description')} />
      </Field>
      <button
        className="btn primary"
        onClick={() => {
          if (!form.job_title || !form.organisation) return
          const body = Object.fromEntries(
            Object.entries(form).map(([k, v]) => [k, v === '' ? null : v]),
          )
          body.job_title = form.job_title
          body.organisation = form.organisation
          body.status = form.status
          onSave(body)
        }}
      >
        Save application
      </button>
    </div>
  )
}
