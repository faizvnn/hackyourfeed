"""ClipRadar API.

POST /jobs          {"url": "<youtube url>"}  -> Job
GET  /jobs/{id}                               -> Job (poll this; fields fill in per stage)
GET  /renders/{file}                          -> rendered mp4
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import jobs
from .config import RENDER_DIR
from .contracts import Job

app = FastAPI(title="ClipRadar")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
RENDER_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/renders", StaticFiles(directory=RENDER_DIR), name="renders")


class CreateJob(BaseModel):
    url: str


@app.post("/jobs", response_model=Job)
def create_job(body: CreateJob) -> Job:
    return jobs.create(body.url)


@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = jobs.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job


@app.get("/health")
def health() -> dict:
    return {"ok": True}
