/**
 * components/ParagraphHighlight.jsx
 * -----------------------------------
 * Renders a paragraph of text. If the paragraph is flagged, wraps the
 * content in a coloured <mark> element with a tooltip indicating the concern.
 */
export default function ParagraphHighlight({ text, isSuspicious, isAiGenerated }) {
  const markClass = isAiGenerated ? 'ai-generated' : isSuspicious ? 'suspicious' : null

  return (
    <p style={{ marginBottom: '1em' }}>
      {markClass ? (
        <mark
          className={markClass}
          title={
            isAiGenerated
              ? 'Possible AI-generated text detected in this paragraph'
              : 'Possible paraphrase detected in this paragraph'
          }
        >
          {text}
        </mark>
      ) : (
        text
      )}
    </p>
  )
}
