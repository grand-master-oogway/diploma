# firms_api

Talking to NASA FIRMS. The MAP_KEY is part of every URL, so every error message built here has it redacted.

- `client.py`: `fetch` (area download, retries on network errors / 429 / 5xx), `fetch_availability`, `fetch_key_status`, CSV validation.
- `models.py`: typed results (`FirmsResponse`, `Availability`, `KeyStatus`).
