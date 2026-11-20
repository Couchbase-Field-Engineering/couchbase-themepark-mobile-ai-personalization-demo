# Nightly export landing folder

`exportTime=YYYYMMDD/` partitions of the `parkchat_people` dataset - one JSON
Lines row per guest, trip planner or crew member - delivered by the
nightly export from the systems of record (see datagen/README.md), or written
locally by `datagen/generate_mock_export.py`: `part-*.json` files, `_SUCCESS`
and `_manifest.json`. The backend mounts this folder read-only at
`/data/parkchat-export` and loads the newest complete partition on startup and
whenever a newer one appears.
