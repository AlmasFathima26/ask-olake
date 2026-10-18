source: https://olake.io/docs/fusion/getting-started/overview/
# OLake Fusion Overview

OLake Fusion is an automated Apache Iceberg table maintenance platform. Iceberg
tables can accumulate small files, delete files, and excess metadata as data
ingestion, updates, and deletes continue; these can degrade query performance
and increase storage overhead.

The official guide recommends considering maintenance when there is frequent
ingestion or updating, an accumulation of small or delete files, high partition
cardinality, degrading query performance, or growing table size. Iceberg
Maintenance in the OLake UI is available starting from version 0.4.0.
