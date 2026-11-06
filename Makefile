.PHONY: setup dev stage

setup:
	cd backend && uv sync
	@test -f backend/.env || cp .env.example backend/.env
	@which ffmpeg >/dev/null || echo ">>> brew install ffmpeg"

dev:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

# make stage N=3        (add SAVE=1 to overwrite that stage's fixture)
stage:
	cd backend && uv run python scripts/run_stage.py $(N) $(if $(SAVE),--save,) $(URL)
