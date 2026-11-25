locals {
  # One spec per table, generated from the Python table definitions by `firms-ua bq-schemas`.
  specs  = { for f in fileset("${path.module}/schemas", "*.json") : trimsuffix(f, ".json") => jsondecode(file("${path.module}/schemas/${f}")) }
  layers = toset([for s in local.specs : s.layer])
}

# BigLake: the connection's own service account reads the buckets, so people need BigQuery roles only.
resource "google_bigquery_connection" "lake" {
  project       = var.project_id
  connection_id = "${var.project_name}-${var.env}-lake"
  location      = var.region
  friendly_name = "FIRMS lake (${var.env})"
  description   = "Read-only access from BigQuery to the bronze and silver Parquet files."

  cloud_resource {}
}

resource "google_storage_bucket_iam_member" "lake_read" {
  for_each = local.layers

  bucket = var.buckets[each.key]
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_bigquery_connection.lake.cloud_resource[0].service_account_id}"
}

resource "google_bigquery_dataset" "layer" {
  for_each = local.layers

  project                    = var.project_id
  dataset_id                 = "${var.env}_${each.key}"
  location                   = var.region
  description                = "FIRMS ${each.key} layer: external tables over gs://${var.buckets[each.key]} (no data stored in BigQuery)."
  labels                     = var.labels
  delete_contents_on_destroy = false
}

# External tables over the Hive-partitioned Parquet files. The schema lists the file columns only; BigQuery adds the
# partition columns from the folder names (typed by the CUSTOM key spec), which `ignore_auto_generated_schema` keeps
# out of the diff. Metadata caching stays off (the default), so queries always see the current files.
resource "google_bigquery_table" "external" {
  for_each = local.specs

  project                      = var.project_id
  dataset_id                   = google_bigquery_dataset.layer[each.value.layer].dataset_id
  table_id                     = each.value.table
  description                  = each.value.description
  labels                       = var.labels
  deletion_protection          = false # dev; the table holds no data, only a pointer to the files
  schema                       = jsonencode(each.value.schema)
  ignore_auto_generated_schema = true

  external_data_configuration {
    source_format = "PARQUET"
    autodetect    = false
    connection_id = google_bigquery_connection.lake.name
    source_uris   = ["gs://${var.buckets[each.value.layer]}/${each.value.path}/*"]

    hive_partitioning_options {
      mode                     = "CUSTOM"
      source_uri_prefix        = "gs://${var.buckets[each.value.layer]}/${each.value.path}/${each.value.hive_keys}"
      require_partition_filter = false
    }
  }

  depends_on = [google_storage_bucket_iam_member.lake_read]
}

# People who query: read the tables, run query jobs.
resource "google_bigquery_dataset_iam_member" "analyst_read" {
  for_each = {
    for pair in setproduct(var.analyst_members, tolist(local.layers)) :
    "${pair[0]}|${pair[1]}" => pair
  }

  project    = var.project_id
  dataset_id = google_bigquery_dataset.layer[each.value[1]].dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = each.value[0]
}

resource "google_project_iam_member" "analyst_jobs" {
  for_each = toset(var.analyst_members)

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = each.value
}
