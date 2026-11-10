# FIRMS probe findings (2026-11-10)

Measured with `firms-ua probe` (raw responses and `summary.json` are saved under `firms_meta/probe/<timestamp>/` in the
raw storage). Re-run it before a big backfill, these limits change.

## Source availability (data-availability endpoint)

| Source | First day | Last day |
|---|---|---|
| VIIRS_SNPP_SP | 2012-01-20 | 2026-07-31 |
| VIIRS_SNPP_NRT | 2026-08-01 | 2026-11-02 (S-NPP delivery ended) |
| VIIRS_NOAA20_SP | 2018-04-01 | 2026-07-31 |
| VIIRS_NOAA20_NRT | 2026-08-01 | today |
| VIIRS_NOAA21_SP | **2023-03-01** | 2026-07-31 |
| VIIRS_NOAA21_NRT | 2024-01-17 | today |

NOAA-21 SP does not start in 2022 (earlier assumption); the series for that satellite starts on 2023-03-01.

## NRT retention and overlap

- NOAA-20 and S-NPP NRT start exactly on 2026-08-01, the day after SP ends, so there is no gap today. Whether the NRT start moves forward over
  time is unknown: load the NRT gap now.
- NOAA-21 NRT reaches back to 2024-01-17 and overlaps SP. But NRT is not a full substitute for SP: on 2025-07-15 NRT returned 418 rows and SP 861.
- **Out-of-range requests are silent.** A day before a source starts (or an NRT request for an SP-covered day) returns HTTP 200 with a header
  only, never an error. An empty response alone cannot tell a quiet day from an unavailable one; use the availability ranges and the
  cross-satellite check.

## Cost against the key budget (5,000 transactions per 10 minutes)

- A 1-day request costs **2** transactions, a 5-day request costs **10**: the cost scales with the number of days, not requests, so
  5-day windows save requests but not budget. Reading the status endpoint costs nothing.
- Full history is about 5,700 source-days (S-NPP SP 1,619, NOAA-20 SP 1,619, NOAA-21 SP 1,249, NOAA-21 NRT 1,029, NOAA-20 NRT 102,
  S-NPP NRT 94), so about 11,400 transactions: at least three 10-minute intervals, roughly 30 minutes of throttled requests, about 1,150
  requests with 5-day windows.

## The S-NPP gap

On 2024-07-15, S-NPP SP returned 0 rows, and so did 2024-07-14 and a second fetch of 2024-07-15, while 2024-07-16 had 206 (low) rows and
NOAA-20 / NOAA-21 returned 1,078 / 849. The gap is persistent, so it is a known data outage, not a transient error.

## Not measured here

- NRT update cadence and when a day is complete: needs repeated fetches of one NRT day over its first 24 hours.
