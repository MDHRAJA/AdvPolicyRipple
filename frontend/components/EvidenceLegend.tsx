export default function EvidenceLegend({ compact = false }: { compact?: boolean }) {
  return (
    <div className="evidence-legend" role="note" aria-label="Evidence legend">
      <span className="tag observed">OBSERVED DATA{compact ? '' : ' — sourced context'}</span>
      <span className="tag synthetic">SYNTHETIC AGENTS{compact ? '' : ' — generated'}</span>
      <span className="tag simulation">SIMULATION RESULTS{compact ? '' : ' — model output'}</span>
    </div>
  );
}
