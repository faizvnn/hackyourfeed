.PHONY: setup dev stage renderer

setup:
	cd backend && uv sync
	@test -f backend/.env || cp .env.example backend/.env
	@which ffmpeg >/dev/null || echo ">>> brew install ffmpeg"

dev:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

# make stage N=3        (add SAVE=1 to overwrite that stage's fixture)
stage:
	cd backend && uv run python scripts/run_stage.py $(N) $(if $(SAVE),--save,) $(URL)

# make renderer                 flip stage 6 between classic and adaptive
# make renderer E=adaptive      set it explicitly (classic|adaptive)
# Edits RENDER_ENGINE in backend/.env; restart `make dev` afterwards.
renderer:
	@f=backend/.env; test -f $$f || cp .env.example $$f; \
	cur=$$(grep -E '^RENDER_ENGINE=' $$f | tail -1 | cut -d= -f2 | tr -d '[:space:]'); cur=$${cur:-classic}; \
	new="$(E)"; if [ -z "$$new" ]; then if [ "$$cur" = adaptive ]; then new=classic; else new=adaptive; fi; fi; \
	case "$$new" in classic|adaptive) ;; *) echo "E must be classic or adaptive, got '$$new'"; exit 1;; esac; \
	if grep -qE '^RENDER_ENGINE=' $$f; then sed -e "s/^RENDER_ENGINE=.*/RENDER_ENGINE=$$new/" $$f > $$f.tmp && mv $$f.tmp $$f; \
	else printf '\nRENDER_ENGINE=%s\n' "$$new" >> $$f; fi; \
	echo "renderer: $$cur -> $$new  (backend/.env; restart make dev)"; \
	if [ "$$new" = adaptive ] && ! ffmpeg -hide_banner -h filter=ass 2>/dev/null | grep -q '^Filter'; then \
	  echo ">>> ffmpeg has no libass ('ass' filter); adaptive will fail until ffmpeg is reinstalled with it"; fi
