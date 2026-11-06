# Frontend (team D) — Lovable

The UI is built in Lovable, so this folder only holds the contract and the prompt.
Export the Lovable project here when it's done (optional).

## API contract

Base URL: `http://localhost:8000` (dev) / the GMI box URL (demo). CORS is open.

```
POST /jobs            body {"url": "https://www.youtube.com/watch?v=..."}  -> Job
GET  /jobs/{id}       poll every 2s                                           -> Job
```

`Job.status` moves through:
`queued → ingest → understand → trends → playbook → direct → render → done` (or `error`).

Each stage fills in one field, so the UI can reveal sections as they arrive:

| status reached | field filled | show |
|---|---|---|
| understand | `job.transcript` | title, duration |
| trends | `job.understanding` | niche, topics, topic_map as a timeline |
| playbook | `job.viral` | grid of viral videos (thumbnail_url, handle, views, hook_text) |
| direct | `job.playbook` | hook_patterns, takeaways |
| render | `job.clips` | the 3 clips: title, score, hook_rewrite, on_screen_lines, caption, reason |
| done | `job.clips[].render_url` | `<video>` player + download |

Full shapes: `backend/app/contracts.py`. Sample response to build against: `../backend/fixtures/job.json`.

## Lovable prompt (starting point)

> Build a single-page app called ClipRadar. One text input for a YouTube URL and a "Find my clips" button.
> On submit, POST `{url}` to `{API}/jobs`, then poll `GET {API}/jobs/{id}` every 2 seconds.
> Show a vertical stepper with the stages: Ingest, Understand, Pull trends, Build playbook, Pick clips, Render.
> Highlight the current `status`. As each field on the job appears, reveal a section below the stepper:
> niche + topics as chips; a grid of viral videos (thumbnail, handle, views, hook_text); the playbook's hook_patterns as cards with examples and takeaways as a list;
> then the 3 clips as large cards with score badge, hook_rewrite as the headline, on_screen_lines, caption with a copy button, reason, and a 9:16 `<video>` when render_url exists.
> Dark theme, big type, feels like an analytics tool. Use this sample JSON for mock data: (paste fixtures/job.json)
