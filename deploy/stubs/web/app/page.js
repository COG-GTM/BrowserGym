export const dynamic = "force-dynamic";

async function apiHealth() {
  const base = process.env.SIDE_API_URL || "http://localhost:8000/api/v1";
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store" });
    return { base, status: res.status, body: await res.json() };
  } catch (e) {
    return { base, error: String(e) };
  }
}

export default async function Page() {
  const health = await apiHealth();
  return (
    <main>
      <h1>Side — deploy stub</h1>
      <p>Placeholder for apps/web, used only to smoke-test the web image.</p>
      <h2>API health (server-side fetch)</h2>
      <pre data-testid="api-health">{JSON.stringify(health, null, 2)}</pre>
    </main>
  );
}
