import { Suspense } from 'react';
import Simulator from './Simulator';

export default function SimulatePage() {
  return <Suspense fallback={<main className="page-shell"><div className="loading-card">Loading simulation workspace…</div></main>}><Simulator /></Suspense>;
}
