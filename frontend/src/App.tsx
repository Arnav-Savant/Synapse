import { HealthCheck } from "./routes/HealthCheck";

export function App() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold text-slate-800">Synapse</h1>
      <p className="mt-1 text-sm text-slate-500">Phase 0 — scaffolding</p>
      <section className="mt-6 rounded-lg border border-slate-200 p-4">
        <HealthCheck />
      </section>
    </main>
  );
}
