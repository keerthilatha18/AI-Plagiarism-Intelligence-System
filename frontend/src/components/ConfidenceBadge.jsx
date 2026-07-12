/**
 * components/ConfidenceBadge.jsx
 * --------------------------------
 * Displays a colour-coded confidence score:
 *   >= 0.75 → red   (high concern)
 *   >= 0.40 → yellow (medium concern)
 *   <  0.40 → green  (low concern)
 */
export default function ConfidenceBadge({ confidence }) {
  if (confidence === null || confidence === undefined) return null

  const pct = Math.round(confidence * 100)
  let cls = 'badge-green'
  if (confidence >= 0.75) cls = 'badge-red'
  else if (confidence >= 0.40) cls = 'badge-yellow'

  return (
    <span className={`badge ${cls}`} title={`Confidence: ${pct}%`}>
      {pct}%
    </span>
  )
}
