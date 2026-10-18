source: https://olake.io/docs/
# OLake Go Sources and Sync Modes

The official OLake Go overview lists these source connectors and modes:

| Source | Full Refresh | Full Refresh + Incremental | Full Refresh + CDC | CDC Only |
| --- | --- | --- | --- | --- |
| PostgreSQL | Yes | Yes | Yes | Yes |
| MySQL | Yes | Yes | Yes | Yes |
| MongoDB | Yes | Yes | Yes | Yes |
| Oracle Database | Yes | Yes | No | No |
| Apache Kafka | No | No | No | Yes |
| DB2 | Yes | Yes | No | No |
| MSSQL | Yes | Yes | Yes | Yes |
| S3 | Yes | Yes | No | No |

Do not infer that every connector supports every mode. Consult the relevant
connector guide for its current configuration and prerequisites:

- [PostgreSQL](https://olake.io/docs/connectors/postgres/)
- [MySQL](https://olake.io/docs/connectors/mysql/)
- [MongoDB](https://olake.io/docs/connectors/mongodb/)
- [Oracle](https://olake.io/docs/connectors/oracle/)
- [MSSQL](https://olake.io/docs/connectors/mssql/)
- [IBM Db2](https://olake.io/docs/connectors/db2/)
- [Apache Kafka](https://olake.io/docs/connectors/kafka/)
- [S3](https://olake.io/docs/connectors/s3/)
