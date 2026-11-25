# Querying the lake in BigQuery

Bronze and silver are BigLake external tables: BigQuery reads the Parquet files in the buckets at query time, nothing
is copied or stored in BigQuery. Defined in `infra/modules/bigquery` (applied by CI after merge).

| BigQuery table | Files | Partition column |
|---|---|---|
| `nasa-firms.dev_bronze.firms_viirs` | `gs://firms-ua-dev-bronze/firms_viirs/v1/` | `source` (STRING), `acq_date` (STRING) |
| `nasa-firms.dev_silver.firms_detections` | `gs://firms-ua-dev-silver/firms_detections/v1/` | `acq_date` (DATE) |
| `nasa-firms.dev_silver.h3_r9_daily_activity` | `gs://firms-ua-dev-silver/h3_r9_daily_activity/v1/` | `acq_date` (DATE) |

Access: add your account to `analyst_members` (Terraform variable), then use the BigQuery console. Filtering on the
partition column reads only those days' files.

## Example queries

Rows per day (compare with the `firms_silver` run metadata in Dagster):

```sql
SELECT acq_date, product, COUNT(*) AS rows
FROM `nasa-firms.dev_silver.firms_detections`
WHERE acq_date >= DATE '2026-11-01'
GROUP BY acq_date, product
ORDER BY acq_date DESC;
```

Preferred detections inside Ukraine per Kyiv day, without static industrial sources and fill values:

```sql
SELECT acq_date_kyiv, COUNT(*) AS detections, ROUND(SUM(frp), 1) AS frp_mw
FROM `nasa-firms.dev_silver.firms_detections`
WHERE acq_date BETWEEN DATE '2026-10-31' AND DATE '2026-11-24'
  AND is_preferred AND in_ukraine AND NOT is_persistent_hotspot AND NOT flag_invalid_brightness
GROUP BY acq_date_kyiv
ORDER BY acq_date_kyiv;
```

Most active H3 r7 cells in a month (cell ids are INT64; H3 ids are below 2^63, so nothing is lost):

```sql
SELECT h3_r7, COUNT(*) AS detections, COUNT(DISTINCT acq_date_kyiv) AS days
FROM `nasa-firms.dev_silver.firms_detections`
WHERE acq_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31' AND is_preferred AND in_ukraine
GROUP BY h3_r7
ORDER BY detections DESC
LIMIT 20;
```

Points on a map: select `ST_GEOGPOINT(longitude, latitude) AS geom` and open the result in BigQuery Geo Viz or
Looker Studio. A point is the center of a ~375 m pixel, not the location of a fire; keep published views aggregated
(H3 r6/r7, at least one day).

Silver against bronze for one day (bronze is all strings):

```sql
SELECT source, COUNT(*) AS bronze_rows
FROM `nasa-firms.dev_bronze.firms_viirs`
WHERE acq_date = '2026-11-20'
GROUP BY source;
```

## Cost and caveats

- On-demand queries bill the bytes read (the first 1 TiB per month is free). The whole lake is tens of MB, so normal
  use costs nothing. Bronze objects older than the Coldline threshold add a small retrieval fee per GB read.
- Replacing a silver day is not atomic: a query that runs while that day is being rebuilt can briefly see it twice.
- Types follow the table definitions (`firms-ua bq-schemas`): enums are STRING, Float32 becomes FLOAT64, unsigned
  integers become INT64, UTC datetimes TIMESTAMP.
