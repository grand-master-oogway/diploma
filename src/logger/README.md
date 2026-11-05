# logger

`configure_logging(level)` sets up console logging (stderr) and nothing else: no log files. Call it once at an entry point (the CLI does). Modules just use `logging.getLogger(__name__)`.

`urllib3` and `requests` are pinned to WARNING because their DEBUG output contains request URLs, and the FIRMS MAP_KEY is part of the URL. Level comes from `FIRMS_LOG_LEVEL` (default `INFO`).
