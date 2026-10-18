source: https://olake.io/blog/exactly-once-delivery-iceberg/
# Checkpoint Recovery After an OLake Sync Interruption

OLake Go commits Iceberg data and a progress marker atomically, then saves the
same progress to `state.json`. If the process stops after the Iceberg commit
but before the checkpoint file is updated, the destination can be ahead of
`state.json`.

On the next run, OLake compares the Iceberg marker with `state.json`. If Iceberg
is ahead, it skips already committed work and repairs the checkpoint without
re-reading the source or writing duplicate data. The official article says
this recovery pattern applies to Full Refresh, Incremental, and CDC syncs.
