import { backendUrl, readSample } from "@/lib/engine";
import { fromBackend } from "@/lib/backend";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  if (id.startsWith("sample-")) {
    const job = readSample(id);
    return job ? Response.json(job) : Response.json({ error: "not_found" }, { status: 404 });
  }

  const base = backendUrl();
  if (!base) return Response.json({ error: "engine_offline" }, { status: 503 });
  try {
    const r = await fetch(`${base}/jobs/${encodeURIComponent(id)}`, { cache: "no-store", signal: AbortSignal.timeout(15000) });
    if (r.status === 404) return Response.json({ error: "not_found" }, { status: 404 });
    if (!r.ok) return Response.json({ error: "engine_failed" }, { status: 502 });
    return Response.json(fromBackend(await r.json(), base));
  } catch {
    return Response.json({ error: "engine_unreachable" }, { status: 502 });
  }
}
