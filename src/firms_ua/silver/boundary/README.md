# boundary

`ukraine_adm0.geojson`: the Ukraine border polygon used by `silver/border.py` (lon/lat, CRS84).

- Source: geoBoundaries gbOpen, UKR ADM0, boundary id `UKR-ADM0-60985579`, simplified geometry
  (https://www.geoboundaries.org/api/current/gbOpen/UKR/ADM0/, snapshot built 2026-11-02, downloaded 2026-11-25).
- Underlying data: OpenStreetMap (via Wambacher), boundary year 2017. License: Open Data Commons Open Database
  License 1.0 (ODbL), attribution "© OpenStreetMap contributors, geoBoundaries".
- Coverage: internationally recognised borders, Crimea and the occupied territories included, **plus the 12 nmi
  territorial sea** (area about 640,000 km2 against about 604,000 km2 of land).
- sha256: `f30a4fabc64d72e67167f6627f778efdf49ed0af178030fc5b48be5d82682cfc` (checked by a test; written into every
  silver file's metadata). `.gitattributes` keeps the bytes as-is (`-text`).

To replace it, put the new file here, update `BOUNDARY_NAME` in `border.py`, the hash in the test and this README, and
rebuild silver.
