# Inspect episodes in Foxglove

Every file the pipeline writes is deliberately standard MCAP with in-band
H.264 video, so episode inspection is an existing tool, not an HFlow UI.
This page gets you from "the pipeline processed something" to scrubbing
through that episode's camera and data streams in
[Foxglove](https://foxglove.dev/).

This is one of the system's three inspection surfaces. The other two have
their own pages: watching **runs** happens in
[Airflow's UI](../RUNTIME.md#the-loop), and querying the recorded **evidence**
(measurements, quarantine status, intervals) happens
[with DuckDB over the catalog](../CATALOG.md#querying).

## 1. Find the canonical file

Where an episode lands depends on how it was processed:

| Entry point | Canonical episode path |
|---|---|
| `app.test(...)` (dev loop) | `<data_root>/test-runs/<stem>-<source-hash>/<stem>.canonical.mcap` |
| `app.process(...)` / the ingest DAG | `<data_root>/episodes/<stem>-<source-hash>/<stem>.canonical.mcap` |

`<source-hash>` is a short digest of where the source came from, so equal
basenames from different sources never collide; a shell glob finds the
directory without computing it (`test-runs/<stem>-*/`).

For a bucket data root (`gs://`, `s3://`, Azure), the same layout lives under
the bucket prefix. Download the file with your provider's CLI and open it
locally.

If a file misbehaves in any viewer, check conformance before blaming the
viewer:

```bash
uv run hflow doctor path/to/episode.canonical.mcap
```

## 2. Open it

Use the Foxglove desktop app or [app.foxglove.dev](https://app.foxglove.dev)
in a browser, and open the `.mcap` as a local file. No conversion, plugin, or
upload step: camera streams are [`foxglove.CompressedVideo`](https://docs.foxglove.dev/docs/sdk/schemas/compressed-video)
messages, which Foxglove plays natively, and every other channel appears
under its recorded topic name.

Useful panels:

- **Image**: select the camera topic and press play; the playback bar scrubs
  the whole episode.
- **Plot**: graph numeric series such as joint states over time.
- **Raw Messages**: the decoded payload of any topic, message by message.

[Rerun](https://rerun.io/) also opens the same files, and so does any
conforming MCAP reader: the canonical writer changes chunking layout for
read performance, never the format.

## 3. Read it next to the evidence

The file contains the recording; the *judgments* about it live in the
catalog. An episode's quarantine status, measurements, and labeled intervals
(camera freezes, timestamp gaps) are rows you [query with
DuckDB](../CATALOG.md#querying). The working loop is to find a suspicious
episode in SQL, then open exactly that file here and scrub to the interval
the check flagged.

For a worked pass over real footage (including two fault types to look at
and the SQL that finds them), run the
[egocentric factory corpus example](../../examples/egocentric/README.md).
