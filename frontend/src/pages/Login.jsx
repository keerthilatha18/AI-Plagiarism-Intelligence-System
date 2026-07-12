/**
 * pages/Login.jsx
 * ---------------
 * Simple mock instructor login page.
 * Stores instructor_id in localStorage — no real authentication.
 * Replace with IBM App ID or your auth provider in production.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const MOCK_INSTRUCTORS = [
  { id: 'inst-alice', name: 'Prof. Alice Chen', dept: 'Computer Science' },
  { id: 'inst-bob',   name: 'Prof. Bob Martinez', dept: 'History' },
]

export default function Login() {
  const [selected, setSelected] = useState('')
  const navigate = useNavigate()

  function handleLogin(e) {
    e.preventDefault()
    if (!selected) return
    localStorage.setItem('instructor_id', selected)
    const instructor = MOCK_INSTRUCTORS.find(i => i.id === selected)
    localStorage.setItem('instructor_name', instructor?.name || selected)
    navigate('/')
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f7f8fa' }}>
      <div className="card" style={{ width: 360 }}>
        <div style={{ marginBottom: 20, textAlign: 'center' }}>
          <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>Plagiarism Intelligence</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13 }}>Sign in as instructor</p>
        </div>

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label htmlFor="instructor-select">Select instructor account</label>
            <select
              id="instructor-select"
              value={selected}
              onChange={e => setSelected(e.target.value)}
            >
              <option value="">-- choose --</option>
              {MOCK_INSTRUCTORS.map(i => (
                <option key={i.id} value={i.id}>
                  {i.name} — {i.dept}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center' }}
            disabled={!selected}
          >
            Sign in
          </button>
        </form>

        <p style={{ marginTop: 12, fontSize: 12, color: 'var(--muted)', textAlign: 'center' }}>
          This is a demo login — no password required.
        </p>
      </div>
    </div>
  )
}
