source: https://olake.io/docs/connectors/postgres/
# PostgreSQL Connector

The OLake PostgreSQL source connector supports Full Refresh, Full Refresh +
CDC, CDC Only, and Full Refresh + Incremental. PostgreSQL server version 10
or newer is required.

The current connector guide recommends the native `pgoutput` plugin for CDC
and says the older `wal2json`-based method is deprecated.

For CDC, configure a logical replication slot using `pgoutput` and a
publication in the same database. The publication must include the tables to
capture. The PostgreSQL user also needs read access to the selected tables.

The connector configuration includes a required database host, port, database
name, username, and password. The guide also documents schemas, JDBC URL
parameters, and SSL mode configuration.
