# common

Code every other package may use and that depends on none of them.

- `settings.py`: `Settings` (environment / `.env`), including the MAP_KEY lookup (environment first, then Secret Manager).
- `secrets.py`: read a secret from Secret Manager with Application Default Credentials; `clean_secret` strips whitespace, a BOM and quotes.
- `errors.py`: project errors (`FirmsError`, `SchemaError`).
- `windows.py`: `Window` and `plan_windows` (split a date range into request windows).
- `sources.py`: satellites (NOAA-20, NOAA-21, S-NPP) and which FIRMS source serves each day: SP up to 2026-07-31, NRT after; NOAA-21
  starts on 2023-03-01 (its first SP day), S-NPP stops on its last delivery day (`FIRMS_SNPP_LAST_DAY`). `windows_for` plans windows on a
  fixed 5-day grid from 2022-02-24 so window keys stay the same between runs.
