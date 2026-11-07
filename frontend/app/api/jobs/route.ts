import { backendUrl, SAMPLE_YOUTUBE_ID, startSample, youtubeId } from "@/lib/engine";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as { url?: string };
  const url = String(body.url ?? "").trim();
  const vid = youtubeId(url);
  if (!vid) return Response.json({ error: "bad_link" }, { status: 400 });

  const base = backendUrl();
  if (!base) {
    if (vid !== SAMPLE_YOUTUBE_ID) return Response.json({ error: "engine_offline" }, { status: 503 });
    return Response.json({ id: startSample() });
  }

  try {
    const r = await fetch(`${base}/jobs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
      signal: AbortSignal.timeout(20000),
    });
    const data = (await r.json().catch(() => ({}))) as { id?: string; job_id?: string; detail?: unknown };
    const id = data.id ?? data.job_id;
    if (!r.ok || !id) return Response.json({ error: "engine_failed", detail: data.detail ?? null }, { status: 502 });
    return Response.json({ id });
  } catch {
    return Response.json({ error: "engine_unreachable" }, { status: 502 });
  }
}
