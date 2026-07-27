import { useState } from 'react'
import { api } from '../api'
import { BarRows, Card, Empty, Field, Tags, Tile, label, pct } from './ui'

export default function Resumes({ resumes, stats, jobs, reload }) {
  const [expanded, setExpanded] = useState(null)
  const [adding, setAdding] = useState(false)

  const versionRows = (stats.by_version ?? [])
    .filter((v) => v.applications > 0)
    .map((v) => ({
      label: v.version_label ? `${v.name} (${v.version_label})` : v.name,
      value: v.applications,
      rate: v.response_rate,
    }))

  return (
    <>
      <div className="tiles">
        <Tile label="Versions" value={stats.total_versions ?? 0} note={`${stats.master_versions ?? 0} master`} />
        <Tile
          label="Tailoring runs"
          value={stats.tailoring_entries ?? 0}
          note={`${stats.tailoring_applied ?? 0} applied`}
        />
        <Tile
          label="Unattributed"
          value={stats.jobs_without_resume ?? 0}
          note="applications with no version recorded"
        />
      </div>

      <Card title="Response rate by version" sub="Which resume actually gets replies">
        <BarRows
          items={versionRows}
          empty="No version has been sent to an application yet."
          formatValue={(i) => `${i.value} sent · ${i.rate}% reply`}
        />
      </Card>

      <div style={{ marginTop: 16 }}>
        <Card
          title="Resume versions"
          sub="Paste the text so the assistant can tailor it against a job description"
          actions={
            <button className="btn primary" onClick={() => setAdding((v) => !v)}>
              {adding ? 'Cancel' : 'Add version'}
            </button>
          }
        >
          {adding && (
            <ResumeForm
              onSave={async (body) => {
                await api.resumes.create(body)
                setAdding(false)
                reload()
              }}
            />
          )}

          {resumes.length === 0 ? (
            <Empty>
              No resume versions yet. Add one with its text, then ask the assistant to tailor it
              for a specific role.
            </Empty>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Target role</th>
                  <th className="num">Sent</th>
                  <th className="num">Reply rate</th>
                  <th className="num">Tailoring</th>
                </tr>
              </thead>
              <tbody>
                {resumes.map((resume) => {
                  const s = (stats.by_version ?? []).find((v) => v.id === resume.id) ?? {}
                  return (
                    <ResumeRow
                      key={resume.id}
                      resume={resume}
                      versionStats={s}
                      jobs={jobs}
                      open={expanded === resume.id}
                      onToggle={() => setExpanded(expanded === resume.id ? null : resume.id)}
                      reload={reload}
                    />
                  )
                })}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  )
}

function ResumeRow({ resume, versionStats, jobs, open, onToggle, reload }) {
  return (
    <>
      <tr className="clickable" onClick={onToggle}>
        <td>
          <div className="row-main">
            {resume.name}
            {resume.is_master && <span className="tag" style={{ marginLeft: 8 }}>master</span>}
          </div>
          <div className="row-sub">
            {resume.version_label || 'no label'} · created {resume.created_date}
            {resume.content ? ` · ${resume.content.length} chars` : ' · no text stored'}
          </div>
        </td>
        <td className="small">{resume.target_role || '—'}</td>
        <td className="num">{versionStats.applications ?? 0}</td>
        <td className="num">{pct(versionStats.response_rate)}</td>
        <td className="num">{resume.tailoring.length}</td>
      </tr>
      {open && (
        <tr className="detail">
          <td colSpan={5}>
            <div style={{ padding: '6px 4px 10px' }}>
              <div className="detail-inner" style={{ padding: 0 }}>
                <div>
                  <h4>Resume text</h4>
                  <textarea
                    defaultValue={resume.content}
                    placeholder="Paste the resume text here so it can be tailored against a JD"
                    style={{ minHeight: 160 }}
                    onBlur={async (e) => {
                      if (e.target.value !== resume.content) {
                        await api.resumes.update(resume.id, { content: e.target.value })
                        reload()
                      }
                    }}
                  />
                  <div className="field-row" style={{ marginTop: 10 }}>
                    <Field label="Target role">
                      <input
                        defaultValue={resume.target_role ?? ''}
                        onBlur={async (e) => {
                          await api.resumes.update(resume.id, {
                            target_role: e.target.value || null,
                          })
                          reload()
                        }}
                      />
                    </Field>
                    <Field label="File path">
                      <input
                        defaultValue={resume.file_path ?? ''}
                        onBlur={async (e) => {
                          await api.resumes.update(resume.id, { file_path: e.target.value || null })
                          reload()
                        }}
                      />
                    </Field>
                  </div>
                  <button
                    className="btn small ghost"
                    style={{ color: 'var(--critical)' }}
                    onClick={async () => {
                      if (confirm(`Delete "${resume.name}"?`)) {
                        await api.resumes.remove(resume.id)
                        reload()
                      }
                    }}
                  >
                    Delete version
                  </button>
                </div>

                <div style={{ gridColumn: 'span 2' }}>
                  <h4>Tailoring against job descriptions</h4>
                  {resume.tailoring.length === 0 && (
                    <p className="muted small">
                      None yet. Ask the assistant: “tailor my {resume.name} for the{' '}
                      {jobs[0]?.organisation ?? '…'} role”.
                    </p>
                  )}
                  {resume.tailoring.map((entry, index) => (
                    <div
                      key={index}
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-sm)',
                        padding: 12,
                        marginBottom: 10,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          marginBottom: 8,
                        }}
                      >
                        <strong className="small">{entry.organisation || 'Unlinked'}</strong>
                        <span className="when small muted">{entry.date}</span>
                        <span style={{ flex: 1 }} />
                        <label className="small">
                          <input
                            type="checkbox"
                            checked={entry.applied}
                            onChange={async (e) => {
                              await api.resumes.setApplied(resume.id, index, e.target.checked)
                              reload()
                            }}
                            style={{ width: 'auto', marginRight: 6 }}
                          />
                          Applied
                        </label>
                      </div>
                      {entry.missing_keywords.length > 0 && (
                        <div className="small" style={{ marginBottom: 8 }}>
                          <span className="muted">Missing keywords: </span>
                          <Tags items={entry.missing_keywords} />
                        </div>
                      )}
                      {entry.suggestions.map((s, i) => (
                        <div className="list-note" key={i}>
                          <div className="when">{s.section}</div>
                          {s.change}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function ResumeForm({ onSave }) {
  const [form, setForm] = useState({
    name: '',
    version_label: '',
    target_role: '',
    content: '',
    is_master: false,
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
        <Field label="Name">
          <input value={form.name} onChange={set('name')} placeholder="SDE — backend heavy" />
        </Field>
        <Field label="Version label">
          <input value={form.version_label} onChange={set('version_label')} placeholder="v1" />
        </Field>
        <Field label="Target role">
          <input value={form.target_role} onChange={set('target_role')} />
        </Field>
      </div>
      <Field label="Resume text">
        <textarea value={form.content} onChange={set('content')} style={{ minHeight: 120 }} />
      </Field>
      <label className="small" style={{ display: 'block', marginBottom: 12 }}>
        <input
          type="checkbox"
          checked={form.is_master}
          onChange={(e) => setForm({ ...form, is_master: e.target.checked })}
          style={{ width: 'auto', marginRight: 6 }}
        />
        This is a master version
      </label>
      <button
        className="btn primary"
        onClick={() => {
          if (!form.name) return
          onSave({ ...form, target_role: form.target_role || null })
        }}
      >
        Save version
      </button>
    </div>
  )
}
