# ops

Checks you run around the pipeline, not part of the data flow.

- `probe.py`: measure what FIRMS actually serves (availability, NRT retention, request cost, the S-NPP gap); saves raw responses and a summary.
- `bronze_profile.py`: statistics of bronze (versions per source, UTC overpass hours, value quantiles, H3 r9 cells by active days per year) that set silver's label tables, value-range checks and hotspot threshold.
- `smoke.py`: check that the current identity can read the key, reach FIRMS and use the buckets it should.
