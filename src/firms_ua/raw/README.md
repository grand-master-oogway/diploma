# raw

The raw layer: the unchanged API response (CSV bytes), one object per request, never overwritten.

- `store.py`: `write_raw`, `read_raw`, `list_raw` and `RawObject`. Key layout:
  `firms/source=<S>/start_date=<D>/day_range=<N>/requested_at=<UTC>.csv`.
