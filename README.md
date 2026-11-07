# ClipRadar

Paste a podcast URL → find out what's going viral in its niche right now (Oriane) → pick and cut the 3 clips that match (GMI Cloud + ffmpeg / Compound.mov).

## Repo layout

```
hackathon/
├── README.md                 ← run instructions, per-team "done when" table, integration plan
├── Makefile                  ← make setup / make dev / make stage N=3 SAVE=1
├── .env.example              ← USE_FIXTURES=all by default; GMI, Oriane, Compound keys
├── docs/oriane-openapi.json
├── frontend/README.md        ← API contract + Lovable prompt (team D)
└── backend/
    ├── app/
    │   ├── contracts.py      ← the shared JSON shapes between every stage
    │   ├── jobs.py           ← in-memory jobs, runs stages 1→6 in a thread
    │   ├── main.py           ← POST /jobs, GET /jobs/{id}, /renders/*
    │   ├── config.py, llm.py (GMI, OpenAI-compatible), fixtures.py
    │   ├── pipeline/
    │   │   ├── s1_ingest.py      team A   yt-dlp → timed transcript + mp4
    │   │   ├── s2_understand.py  team A   LLM → niche, keyword sets, candidate moments
    │   │   ├── s3_oriane.py      team B   3 Oriane searches → compact viral records
    │   │   ├── s4_playbook.py    team B   LLM → hook patterns, pacing, caption formula
    │   │   ├── s5_direct.py      team C   LLM → top 3 clips w/ hook rewrites
    │   │   └── s6_render.py      team C   ffmpeg 9:16 + burned hook + captions; Compound TODO
    │   │       s6_render_adaptive.py  experimental libass captions; RENDER_ENGINE=adaptive (backend/RENDER.md)
    │   └── prompts/ understand.md, playbook.md, direct.md
    ├── fixtures/  transcript, understanding, viral, playbook, clips, clips_rendered, job
    └── scripts/run_stage.py  ← run one stage on the fixture that feeds it
```

## Pipeline

```
YouTube URL
  → [1] ingest      yt-dlp            Transcript        team A
  → [2] understand  LLM               Understanding     team A   (niche + keywords + topic map; no clip picking)
  → [3] trends      Oriane ×3         ViralSet          team B
  → [4] playbook    LLM               Playbook          team B
  → [5] direct      LLM               ClipSet           team C   (scans the full transcript WITH the playbook)
  → [6] render      ffmpeg/Compound   ClipSet + mp4     team C
  → [7] UI          Lovable                             team D
```

## Run it

```bash
make setup          # uv sync, copies .env.example -> backend/.env
make dev            # API on :8000, every stage returns fixtures (USE_FIXTURES=all)
curl -s -X POST localhost:8000/jobs -H 'content-type: application/json' -d '{"url":"https://youtube.com/watch?v=x"}'
curl -s localhost:8000/jobs/<id>
```

Needs `ffmpeg` on PATH for stage 6 (`brew install ffmpeg`).

## How to work on your stage

1. Keep `USE_FIXTURES=all` in `backend/.env`, then **remove your stage's name** so only yours runs for real. Names: `ingest,understand,trends,playbook,direct,render`.
2. Iterate with `make stage N=<n>`: it runs stage *n* on the fixture that feeds it and prints the output. Add `SAVE=1` to overwrite the downstream fixture with real output so the next team gets real data.
3. The contract between stages is `backend/app/contracts.py`. Change it there first; don't pass extra fields around informally.

| Team | Files | Done when |
|---|---|---|
| A — [1,2] | `pipeline/s1_ingest.py`, `s2_understand.py`, `prompts/understand.md` | `make stage N=1 URL=<demo podcast> SAVE=1` then `make stage N=2 SAVE=1` produce real `transcript.json` / `understanding.json` |
| B — [3,4] | `pipeline/s3_oriane.py`, `s4_playbook.py`, `prompts/playbook.md` | **Done (Nov 6):** `make stage N=3 SAVE=1` returns ≥30 real videos with `hook_text` filled; `make stage N=4 SAVE=1` gives 4–6 patterns. Quality now depends on stage 2 emitting spoken phrases, not nouns |
| C — [5,6] | `pipeline/s5_direct.py`, `s6_render.py`, `prompts/direct.md` | `make stage N=5 SAVE=1` then `make stage N=6` writes 3 playable 9:16 mp4s to `backend/work/renders/` |
| D — [7] | `frontend/` (Lovable) | UI runs the full flow against `make dev` with fixtures, shows each section as it arrives |

## Keys

- GMI Cloud: `GMI_BASE_URL`, `GMI_API_KEY`, `GMI_MODEL` — OpenAI-compatible. Use `google/gemini-3.5-flash-lite` (verified for stage 4, ~4 s per playbook, and for video in `analyze_clip.py`). `google/gemini-3.5-flash` returns 400 on long prompts through GMI; see `docs/clip-analysis-notes.md`.
- Oriane: `ORIANE_API_KEY`, sent as `Authorization: Bearer` (`x-api-key` is rejected). Spec: `docs/oriane-openapi.json`, endpoint `POST https://connect.oriane.xyz/rest/contents/search`.
- Compound.mov: `COMPOUND_API_KEY`, used in `s6_render.compound_polish()` (TODO).

## Integration plan

- **min 30:** each team's stage runs on fixtures, `make dev` + UI works end to end on fixtures.
- **min 75:** flip `USE_FIXTURES=` empty on one machine, run the demo podcast for real, fix whatever breaks at the seams.
- **min 100:** freeze. Run the judges' podcasts, keep the outputs as fixtures, demo from those if the live run is slow.
