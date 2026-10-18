source: https://olake.io/docs/connectors/kafka/
# Kafka Connector

The OLake Kafka source connector synchronizes messages from Kafka topics and
supports one synchronization mode. Kafka 2.4.0 or newer is required.

Kafka topics delete messages after their configured retention period. OLake
cannot access or sync messages already deleted by retention, so the sync
schedule must run frequently enough to capture messages before they expire.

OLake Go and Kafka broker servers must be accessible within the same network.
The connector guide describes PLAINTEXT, SASL_PLAINTEXT, and SASL_SSL
authentication options.
