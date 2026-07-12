/**
 * pages/InstructorBaseline.jsx
 * -----------------------------
 * Displays the InstructorBaseline for the logged-in instructor:
 * - Bar chart of grade_distribution (recharts)
 * - Historical flag rate (displayed as a stat card + trend indicator)
 * - Expected style profile values
 * - Rebuild baseline button
 */
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { getBaseline, rebuildBaseline, listSubmissions } from '../api/client.js'

export default function InstructorBaseline() {
  const { instructorId } = useParams()
  const [assignments, setAssignments] = useState([])
  const [selectedAssignment, setSelectedAssignment] = useState('')
  const [baseline, setBaseline] = useState(null)
  const [loading, setLoading] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [error, setError] = useState(null)

  // Load available assignments for this instructor
  useEffect(() => {
    listSubmissions({ instructorId }).then(data => {
      const seen = {}
      for (const sub of data.submissions || []) {
        seen[sub.assignment_id] = true
      }
      const ids = Object.keys(seen)
      setAssignments(ids)
      if (ids.length > 0) setSelectedAssignment(ids[0])
    })
  }, [instructorId])

  useEffect(() => {
    if (!selectedAssignment) return
    setLoading(true)
    setError(null)
    getBaseline(instructorId, selectedAssignment)
      .then(setBaseline)
      .catch(err => {
        setBaseline(null)
        if (!err.message.includes('404')) setError(err.message)
      })
      .finally(() => setLoading(false))
  }, [instructorId, selectedAssignment])

  async function handleRebuild() {
    setRebuilding(true)
    setError(null)
    try {
      await rebuildBaseline(instructorId, selectedAssignment)
      const fresh = await getBaseline(instructorId, selectedAssignment)
      setBaseline(fresh)
    } catch (err) {
      setError(err.message)
    } finally {
      setRebuilding(false)
    }
  }

  // Prepare grade distribution data for bar chart
  const gradeDist = baseline?.grade_distribution || {}
  const gradeChartData = Object.entries(gradeDist).map(([grade, count]) => ({
    grade,
    count: Number(count),
  }))

  const thresholdAdj = baseline?.threshold_adjustments || {}

  return (
    <>
      <nav>
        <span className="brand">Plagiarism Intelligence</span>
        <Link to="/" className="nav-link">Assignments</Link>
      </nav>

      <div className="page">
        <div className="page-header">
          <div>
            <div className="page-title">Instructor Baseline</div>
            <div className="page-sub">{instructorId}</div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              value={selectedAssignment}
              onChange={e => setSelectedAssignment(e.target.value)}
              style={{ width: 220 }}
            >
              {assignments.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
            <button
              className="btn btn-primary"
              onClick={handleRebuild}
              disabled={rebuilding || !selectedAssignment}
            >
              {rebuilding ? 'Rebuilding…' : 'Rebuild Baseline'}
            </button>
          </div>
        </div>

        {error && <div className="error-box">{error}</div>}
        {loading && <div className="loading">Loading baseline…</div>}

        {!loading && !baseline && (
          <div className="empty">
            No baseline yet for this assignment. Click "Rebuild Baseline" to compute one.
          </div>
        )}

        {baseline && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>

            {/* Grade distribution bar chart */}
            <div className="card">
              <div className="card-title">Grade Distribution</div>
              {gradeChartData.length === 0 ? (
                <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 8 }}>No grade data available.</p>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={gradeChartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="grade" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Historical flag rate */}
            <div className="card">
              <div className="card-title">Historical Flag Rate</div>
              <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--accent)', margin: '16px 0 8px' }}>
                {((baseline.historical_flag_rate || 0) * 100).toFixed(1)}%
              </div>
              <p style={{ color: 'var(--muted)', fontSize: 13 }}>
                of past submissions for this assignment were flagged.
              </p>
            </div>

            {/* Expected style profile */}
            <div className="card">
              <div className="card-title">Expected Style Profile</div>
              <table style={{ marginTop: 8 }}>
                <tbody>
                  {Object.entries(baseline.expected_style_profile || {}).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ color: 'var(--muted)', fontSize: 13 }}>{k.replace(/_/g, ' ')}</td>
                      <td style={{ fontWeight: 600 }}>{typeof v === 'number' ? v.toFixed(4) : v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Adaptive threshold adjustments */}
            <div className="card">
              <div className="card-title">Adaptive Threshold Adjustments</div>
              <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
                Accumulated nudges from your flag decisions. Positive = threshold raised (less sensitive).
              </p>
              <table>
                <tbody>
                  {Object.entries(thresholdAdj).map(([type, adj]) => (
                    <tr key={type}>
                      <td style={{ color: 'var(--muted)', fontSize: 13 }}>{type}</td>
                      <td style={{ fontWeight: 600, color: adj > 0 ? 'var(--yellow)' : adj < 0 ? 'var(--red)' : 'var(--muted)' }}>
                        {adj > 0 ? '+' : ''}{adj.toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
