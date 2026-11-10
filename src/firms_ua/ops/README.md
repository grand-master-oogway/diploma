# ops

Checks you run around the pipeline, not part of the data flow.

- `probe.py`: measure what FIRMS actually serves (availability, NRT retention, request cost, the S-NPP gap); saves raw responses and a summary.
- `smoke.py`: check that the current identity can read the key, reach FIRMS and use the buckets it should.
