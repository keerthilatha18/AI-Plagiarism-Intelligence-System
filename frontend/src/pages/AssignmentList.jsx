/**
 * pages/AssignmentList.jsx
 * ------------------------
 * Lists assignments for the logged-in instructor.
 * In this demo, assignments are derived from submissions returned by the API.
 */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listSubmissions, rebuildBaseline } from '../api/client.js'

export default function AssignmentList() {
  const instructorId = localStorage.getItem('instructor_id')
  const instructorName = localStorage.getItem('instructor_name') || instructorId
  const navigate = useNavigate()

  const [assignments, setAssignments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    listSubmissions({ instructorId })
      .then(data => {
        // Aggregate unique assignment IDs from submissions
        const seen = {}
        for (const sub of data.submissions || []) {
          const id = sub.assignment_id
          if (!seen[id]) seen[id] = { id, count: 0 }
          seen[id].count++
        }
        setAssignments(Object.values(seen))
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [instructorId])

  function logout() {
    localStorage.clear()
    navigate('/login')
  }

  return (
    <>
      <nav>
        <span className="brand">Plagiarism Intelligence</span>
        <span style={{ flex: 1 }} />
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>{instructorName}</span>
        <button className="btn btn-outline" style={{ marginLeft: 12 }} onClick={logout}>
          Sign out
        </button>
      </nav>

      <div className="page">
        <div className="page-header">
          <div>
            <div className="page-title">Assignments</div>
            <div className="page-sub">Select an assignment to review submissions</div>
          </div>
          <Link
            to={`/instructors/${instructorId}/baseline`}
            className="btn btn-outline"
          >
            View Baseline
          </Link>
        </div>

        {error && <div className="error-box">{error}</div>}
        {loading && <div className="loading">Loading assignments…</div>}

        {!loading && assignments.length === 0 && (
          <div className="empty">No assignments found. Run the seed script to load sample data.</div>
        )}

        {assignments.map(asgn => (
          <Link
            key={asgn.id}
            to={`/assignments/${asgn.id}/submissions`}
            style={{ textDecoration: 'none' }}
          >
            <div className="card" style={{ cursor: 'pointer' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div className="card-title">{asgn.id}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 13 }}>
                    {asgn.count} submission{asgn.count !== 1 ? 's' : ''}
                  </div>
                </div>
                <span style={{ color: 'var(--accent)', fontSize: 13 }}>View submissions →</span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </>
  )
}
