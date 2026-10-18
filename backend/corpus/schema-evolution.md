source: https://olake.io/docs/features/schema/
# OLake Schema Evolution

OLake Go runs schema discovery at the start of each sync. When a new source
column appears, OLake automatically adds it to the Iceberg schema and starts
writing values for it without requiring user action. Historical rows contain
NULL until the source backfills them.

When a source column is deleted, it remains in the destination schema so old
snapshots remain queryable. A renamed source column is treated as the old
column remaining in the destination and a new column being added with the new
name.
