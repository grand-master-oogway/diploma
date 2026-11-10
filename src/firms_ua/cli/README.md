# cli

`firms-ua <command>` (a console script declared in `pyproject.toml`, installed with the package). `main.py` builds the parser and dispatches; each command module has `register(sub)` and `run(args, settings)`
returning the number of failures (exit code 1 if non-zero).

- `ingest.py`: `fetch`, `build-bronze`, `ingest`.
- `probe.py`: `probe`.
- `smoke.py`: `smoke`.
