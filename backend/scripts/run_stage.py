"""Run one pipeline stage from fixtures, print its output as JSON.

    uv run python scripts/run_stage.py 2          # understand, from fixtures/transcript.json
    uv run python scripts/run_stage.py 3          # oriane, from fixtures/understanding.json
    uv run python scripts/run_stage.py 3 --save   # ...and overwrite fixtures/viral.json with the result

Stages 1 and 6 need a real URL / mp4:
    uv run python scripts/run_stage.py 1 https://www.youtube.com/watch?v=...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.contracts import ClipSet, Playbook, Transcript, Understanding, ViralSet  # noqa: E402
from app.fixtures import load  # noqa: E402
from app.pipeline import s1_ingest, s2_understand, s3_oriane, s4_playbook, s5_direct, s6_render  # noqa: E402

OUT_FIXTURE = {1: "transcript", 2: "understanding", 3: "viral", 4: "playbook", 5: "clips", 6: "clips_rendered"}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    save = "--save" in sys.argv
    stage = int(args[0])

    if stage == 1:
        out = s1_ingest.run(args[1])
    elif stage == 2:
        out = s2_understand.run(load("transcript", Transcript))
    elif stage == 3:
        out = s3_oriane.run(load("understanding", Understanding))
    elif stage == 4:
        out = s4_playbook.run(load("viral", ViralSet))
    elif stage == 5:
        out = s5_direct.run(load("transcript", Transcript), load("understanding", Understanding), load("playbook", Playbook))
    elif stage == 6:
        out = s6_render.run("manual", load("transcript", Transcript), load("clips", ClipSet))
    else:
        raise SystemExit("stage must be 1-6")

    text = out.model_dump_json(indent=1)
    print(text)
    if save:
        path = Path(__file__).resolve().parent.parent / "fixtures" / f"{OUT_FIXTURE[stage]}.json"
        path.write_text(text)
        print(f"\nsaved -> {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
