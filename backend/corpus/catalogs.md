source: https://olake.io/docs/understanding/compatibility-catalogs/
# OLake Destinations and Iceberg Catalogs

OLake writes data to Apache Iceberg tables or plain Parquet files.

The official OLake material lists these Iceberg catalog integrations:
- AWS Glue Data Catalog.
- Apache Hive Metastore.
- REST catalogs, including Nessie, Polaris, Unity Catalog, Lakekeeper, and
  Amazon S3 Tables.
- JDBC catalogs.

Parquet output is written as files to supported storage locations and does not
use an Iceberg catalog. OLake documentation describes Parquet destinations for
Amazon S3, MinIO, Google Cloud Storage, and local filesystems.

The supported catalog implementation and configuration can vary. Consult the
[Iceberg catalog compatibility guide](https://olake.io/docs/understanding/compatibility-catalogs/)
and the relevant [Iceberg writer documentation](https://olake.io/docs/writers/iceberg/).
