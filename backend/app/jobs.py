"""In-memory job store and the sequential pipeline runner."""

from __future__ import annotations

import threading
import traceback
import uuid

from .contracts import Job
from .pipeline import s1_ingest, s2_understand, s3_oriane, s4_playbook, s5_direct, s6_render

JOBS: dict[str, Job] = {}


def create(url: str) -> Job:
    job = Job(id=uuid.uuid4().hex[:8], url=url)
    JOBS[job.id] = job
    threading.Thread(target=_run, args=(job,), daemon=True).start()
    return job


def _run(job: Job) -> None:
    try:
        job.status = "ingest"
        job.transcript = s1_ingest.run(job.url)

        job.status = "understand"
        job.understanding = s2_understand.run(job.transcript)

        job.status = "trends"
        job.viral = s3_oriane.run(job.understanding)

        job.status = "playbook"
        job.playbook = s4_playbook.run(job.viral)

        job.status = "direct"
        job.clips = s5_direct.run(job.transcript, job.understanding, job.playbook)

        job.status = "render"
        job.clips = s6_render.run(job.id, job.transcript, job.clips)

        job.status = "done"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
