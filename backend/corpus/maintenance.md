source: https://olake.io/blog/apache-iceberg-table-maintenance-olake-fusion/
# Apache Iceberg Maintenance Made Easier with OLake Fusion

Streaming ingestion, CDC syncs, and frequent micro-batches can create many
small Parquet files. A large number of small files increases query work,
metadata overhead, and object-storage requests. CDC-heavy workloads can also
accumulate delete files that add read-time overhead.

Compaction rewrites fragmented small files into larger files and resolves
accumulated deletes into the data. OLake Fusion automates Apache Iceberg table
maintenance, including compaction.
