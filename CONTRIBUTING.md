# Contributing to Garuda

## Workflow

- Open an issue first for anything larger than a bug fix or a documentation
  correction.
- Work on a feature branch and open a pull request to `main`. Branches are kept
  after merge.
- CI must pass: schema validation of every committed dataset
  (`tools/validate_schema.py`), the pytest suite (`python -m pytest tests -q`),
  the data-core regression (`tests/verify_data_core.jl`) and the maluku 2030
  dispatch headline check (±1 %, `tests/check_dispatch_headlines.jl`). If a
  model change legitimately moves the headline numbers, update that check in the
  same pull request and say why.
- Model-behaviour changes are opt-in: add a config flag whose default leaves
  existing reference results unchanged, plus a test that shows the difference.

## Conventions

- `snake_case` for new Python and Julia functions, variables and filenames.
  Legacy model argument and variable names (e.g. `Grid`, `VillageBuild`,
  `vVIL_IMPORT`) are kept for compatibility with configs and downstream
  adapters; do not rename them in unrelated pull requests.
- Runs are configured, never edited into source: a new run key goes in the
  config / `scenario_*.yml` files and in `PASSTHROUGH_KEYS` in both
  `generate_jobs.py` and `generate_jobs_local.py`.
- Do not commit run outputs (`results/`, `jobs/`), logs, `.DS_Store`,
  `__pycache__/` or large GIS layers.
- Input CSVs under `data_indonesia/` that overlap
  [Power-Lab/data-indonesia-2025](https://github.com/Power-Lab/data-indonesia-2025)
  must stay byte-identical: do not let an editor or formatter rewrite their
  whitespace or line endings.
- `data_indonesia/captive/LICENSE` is the upstream notice for vendored data;
  keep it.

## Licence

Contributions are released under the MIT Licence in [`LICENSE`](LICENSE).
