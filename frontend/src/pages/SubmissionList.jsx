/**
 * pages/SubmissionList.jsx
 * ------------------------
 * Lists submissions for a given assignment.
 * Rows are color-coded by the highest flag confidence:
 *   red   — max confidence >= 0.75
 *   yellow — max confidence >= 0.40
 *   green  — max confidence < 0.40 or no flags
 */
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { listSubmissions, getSubmissionFlags } from '../api/client.js'
import ConfidenceBadge from '../components/ConfidenceBadge.jsx'

function riskClass(maxConfidence) {
  if (maxConfidence === null) return ''
  if (maxConfidence >= 0.75) return 'risk-high'
  if (maxConfidence >= 0.40) return 'risk-med'
  return 'risk-low'
}

export default function SubmissionList() {
  const { assignmentId } = useParams()
  const instructorId = localStorage.getItem('instructor_id')

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function load() {
      try {
        const data = await listSubmissions({ assignmentId, instructorId })
        const subs = data.submissions || []

        // Fetch flags for each submission to determine risk colour
        const enriched = await Promise.all(
          subs.map(async sub => {
            try {
              const flagData = await getSubmissionFlags(sub.submission_id)
              const flags = flagData.flags || []
              const maxConf = flags.length
                ? Math.max(...flags.map(f => f.confidence ?? 0))
                : null
              return { ...sub, flags, maxConf }
            } catch {
              return { ...sub, flags: [], maxConf: null }
            }
          })
        )
        setRows(enriched)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [assignmentId, instructorId])

  return (
    <>
      <nav>
        <span className="brand">Plagiarism Intelligence</span>
        <Link to="/" className="nav-link">Assignments</Link>
      </nav>

      <div className="page">
        <div className="page-header">
          <div>
            <div className="page-title">Submissions</div>
            <div className="page-sub">Assignment: {assignmentId}</div>
          </div>
        </div>

        {error && <div className="error-box">{error}</div>}
        {loading && <div className="loading">Loading submissions…</div>}

        {!loading && rows.length === 0 && (
          <div className="empty">No submissions for this assignment.</div>
        )}

        {!loading && rows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Student ID</th>
                <th>Submitted</th>
                <th>Flags</th>
                <th>Max Confidence</th>
                <th>Risk</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.submission_id} className={riskClass(row.maxConf)}>
                  <td>{row.student_id}</td>
                  <td style={{ fontSize: 12, color: 'var(--muted)' }}>
                    {new Date(row.submitted_at).toLocaleDateString()}
                  </td>
                  <td>{row.flags.length}</td>
                  <td>
                    {row.maxConf !== null
                      ? <ConfidenceBadge confidence={row.maxConf} />
                      : <span style={{ color: 'var(--muted)' }}>—</span>
                    }
                  </td>
                  <td>
                    {row.maxConf === null && <span className="badge badge-gray">No flags</span>}
                    {row.maxConf !== null && row.maxConf >= 0.75 && <span className="badge badge-red">High</span>}
                    {row.maxConf !== null && row.maxConf >= 0.40 && row.maxConf < 0.75 && <span className="badge badge-yellow">Medium</span>}
                    {row.maxConf !== null && row.maxConf < 0.40 && <span className="badge badge-green">Low</span>}
                  </td>
                  <td>
                    <Link to={`/submissions/${row.submission_id}`} className="btn btn-outline" style={{ fontSize: 12 }}>
                      Review
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
