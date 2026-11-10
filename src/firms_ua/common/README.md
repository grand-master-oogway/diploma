# common

Code every other package may use and that depends on none of them.

- `settings.py`: `Settings` (environment / `.env`), including the MAP_KEY lookup (environment first, then Secret Manager).
- `secrets.py`: read a secret from Secret Manager with Application Default Credentials; `clean_secret` strips whitespace, a BOM and quotes.
- `errors.py`: project errors (`FirmsError`, `SchemaError`).
- `windows.py`: `Window` and `plan_windows` (split a date range into request windows).
