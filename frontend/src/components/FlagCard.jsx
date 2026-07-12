/**
 * components/FlagCard.jsx
 * -----------------------
 * Displays a single integrity flag with:
 * - Type badge (paraphrase / ai_generated / style_drift / grade_mismatch)
 * - Confidence meter
 * - Granite explanation text (specific evidence, never a bare boolean)
 * - Confirm / Dismiss buttons — the required human-in-the-loop step
 */
import { useState } from 'react'
import { setFlagDecision } from '../api/client.js'
import ConfidenceBadge from './ConfidenceBadge.jsx'

const FLAG_TYPE_LABELS = {
  paraphrase:     { label: 'Paraphrase',      cls: 'badge-yellow' },
  ai_generated:   { label: 'AI-Generated',    cls: 'badge-red' },
  style_drift:    { label: 'Style Drift',      cls: 'badge-purple' },
  grade_mismatch: { label: 'Grade Mismatch',  cls: 'badge-blue' },
}

export default function FlagCard({ flag, onDecision }) {
  const [deciding, setDeciding] = useState(false)
  const [localDecision, setLocalDecision] = useState(flag.instructor_decision)
  const [error, setError] = useState(null)

  const meta = FLAG_TYPE_LABELS[flag.flag_type] || { label: flag.flag_type, cls: 'badge-gray' }

  async function handleDecision(decision) {
    setDeciding(true)
    setError(null)
    try {
      await setFlagDecision(flag.flag_id, decision)
      setLocalDecision(decision)
      onDecision?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeciding(false)
    }
  }

  const isReviewed = flag.reviewed || localDecision !== null

  return (
    <div
      className="card"
      style={{
        borderLeft: `4px solid ${
          localDecision === 'confirmed' ? 'var(--red)' :
          localDecision === 'dismissed' ? 'var(--green)' :
          'var(--yellow)'
        }`,
        marginBottom: 12,
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span className={`badge ${meta.cls}`}>{meta.label}</span>
        <ConfidenceBadge confidence={flag.confidence} />
        {localDecision === 'confirmed' && (
          <span className="badge badge-red" style={{ marginLeft: 'auto' }}>Confirmed</span>
        )}
        {localDecision === 'dismissed' && (
          <span className="badge badge-green" style={{ marginLeft: 'auto' }}>Dismissed</span>
        )}
        {!localDecision && (
          <span className="badge badge-gray" style={{ marginLeft: 'auto' }}>Pending review</span>
        )}
      </div>

      {/* Granite explanation — always shown, never a bare boolean */}
      <p style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--text)', marginBottom: 10 }}>
        {flag.granite_explanation}
      </p>

      {error && <div className="error-box" style={{ marginBottom: 8 }}>{error}</div>}

      {/* Confirm / Dismiss buttons — only shown if not yet reviewed */}
      {!isReviewed && (
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-danger"
            onClick={() => handleDecision('confirmed')}
            disabled={deciding}
            title="Confirm this flag as a genuine integrity concern"
          >
            Confirm
          </button>
          <button
            className="btn btn-success"
            onClick={() => handleDecision('dismissed')}
            disabled={deciding}
            title="Dismiss this flag as a false positive"
          >
            Dismiss
          </button>
        </div>
      )}

      {isReviewed && (
        <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
          Decision recorded. No automatic action has been taken.
        </p>
      )}
    </div>
  )
}
