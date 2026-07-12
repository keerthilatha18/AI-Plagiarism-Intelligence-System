/**
 * pages/SubmissionDetail.jsx
 * --------------------------
 * Full submission review page.
 * - Displays raw_text with suspicious paragraphs highlighted inline.
 * - Shows each flag as a FlagCard with type, confidence, explanation,
 *   and Confirm/Dismiss buttons.
 * - Buttons call PATCH /flags/{id}/decision — the required human step.
 */
import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getSubmission, getSubmissionFlags, scoreSubmission, processSubmission } from '../api/client.js'
import FlagCard from '../components/FlagCard.jsx'
import ParagraphHighlight from '../components/ParagraphHighlight.jsx'

export default function SubmissionDetail() {
  const { submissionId } = useParams()
  const [submission, setSubmission] = useState(null)
  const [flags, setFlags] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [scoring, setScoring] = useState(false)

  async function loadData() {
    try {
      const [subData, flagData] = await Promise.all([
        getSubmission(submissionId),
        getSubmissionFlags(submissionId),
      ])
      setSubmission(subData)
      setFlags(flagData.flags || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [submissionId])

  async function handleScore() {
    setScoring(true)
    setError(null)
    try {
      // Ensure processed first
      if (!submission?.embedding_vector?.length) {
        await processSubmission(submissionId)
      }
      await scoreSubmission(submissionId)
      await loadData()
    } catch (err) {
      setError(err.message)
    } finally {
      setScoring(false)
    }
  }

  function onDecisionMade() {
    // Reload flags after a decision is recorded
    loadData()
  }

  if (loading) return <div className="page"><div className="loading">Loading…</div></div>

  const paragraphs = (submission?.raw_text || '').split(/\n\n+/)

  // Build a set of paragraph indices that appear in flags
  const flaggedParaIndices = new Set(
    flags
      .filter(f => f.flag_type !== 'style_drift' && f.flag_type !== 'grade_mismatch')
      .flatMap(f => {
        // paragraph index may be embedded in the explanation: "Paragraph 3 …"
        const match = f.granite_explanation?.match(/[Pp]aragraph (\d+)/)
        return match ? [parseInt(match[1], 10) - 1] : []
      })
  )
  const aiParaIndices = new Set(
    flags
      .filter(f => f.flag_type === 'ai_generated')
      .flatMap(f => {
        const match = f.granite_explanation?.match(/[Pp]aragraph (\d+)/)
        return match ? [parseInt(match[1], 10) - 1] : []
      })
  )

  return (
    <>
      <nav>
        <span className="brand">Plagiarism Intelligence</span>
        <Link to="/" className="nav-link">Assignments</Link>
      </nav>

      <div className="page">
        <div className="page-header">
          <div>
            <div className="page-title">Submission Review</div>
            <div className="page-sub">
              ID: {submissionId} &nbsp;·&nbsp;
              Student: {submission?.student_id} &nbsp;·&nbsp;
              Assignment: {submission?.assignment_id}
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleScore}
            disabled={scoring}
          >
            {scoring ? 'Scoring…' : flags.length ? 'Re-score' : 'Score Now'}
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24 }}>

          {/* Left: annotated text */}
          <div>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
              Submission Text
            </h2>
            <div className="card" style={{ fontFamily: 'Georgia, serif', fontSize: 14, lineHeight: 1.8 }}>
              {paragraphs.map((para, i) => (
                <ParagraphHighlight
                  key={i}
                  text={para}
                  isSuspicious={flaggedParaIndices.has(i)}
                  isAiGenerated={aiParaIndices.has(i)}
                />
              ))}
            </div>

            {/* Stylometrics summary */}
            {submission?.style_fingerprint && (
              <div style={{ marginTop: 16 }}>
                <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                  Style Metrics
                </h2>
                <div style={{ display: 'flex', gap: 12 }}>
                  {Object.entries(submission.style_fingerprint).map(([k, v]) => (
                    <div key={k} className="card" style={{ flex: 1, textAlign: 'center' }}>
                      <div style={{ fontSize: 18, fontWeight: 700 }}>{typeof v === 'number' ? v.toFixed(2) : v}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                        {k.replace(/_/g, ' ')}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: flags */}
          <div>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
              Flags ({flags.length})
            </h2>
            {flags.length === 0 && (
              <div className="empty" style={{ fontSize: 13 }}>
                No flags yet.{submission?.embedding_vector?.length
                  ? ' Click "Score Now" to run the pipeline.'
                  : ' Click "Score Now" to process and score.'}
              </div>
            )}
            {flags.map(flag => (
              <FlagCard key={flag.flag_id} flag={flag} onDecision={onDecisionMade} />
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
