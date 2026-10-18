source: https://olake.io/docs/
# Stateful, Resumable Syncs

OLake maintains state for in-progress syncs and resumes automatically from the
last checkpoint after an interruption. This behavior is documented for Full
Refresh + CDC and Full Refresh + Incremental & Strict CDC sync modes.

The documentation says interrupted syncs can resume after crashes, network
failures, or manual pauses, avoiding a full resync from the beginning. This
reduces duplicate processing and improves fault tolerance.
