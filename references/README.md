# Cached third-party references

Local copies of standards this project refers to constantly, so sessions and
agents don't re-fetch them. Each entry records its source and download time;
**treat the upstream URL as authoritative** and re-download (updating the
stamp) when freshness matters.

| File | What | Source | License | Downloaded (UTC) |
|---|---|---|---|---|
| [mcap-spec.md](./mcap-spec.md) | MCAP container format specification | <https://raw.githubusercontent.com/foxglove/mcap/main/website/docs/spec/index.md> (rendered at <https://mcap.dev/spec>) | [MIT](./LICENSE) (foxglove/mcap) | 2026-08-18T07:04Z |
| [foxglove-CompressedVideo.proto](./foxglove-CompressedVideo.proto) | `foxglove.CompressedVideo` schema, including the normative per-codec bitstream constraints (Annex B, SPS on IDR, no B-frames) | <https://raw.githubusercontent.com/foxglove/foxglove-sdk/main/schemas/proto/foxglove/CompressedVideo.proto> | [MIT](./LICENSE) (foxglove/foxglove-sdk) | 2026-08-18T07:04Z |
| [airflow3-notes.md](./airflow3-notes.md) | Airflow 3.x facts for the Compose runtime: our own synthesis with per-fact citations, not a mirror | official Airflow docs (cited inline) | n/a (our text) | 2026-08-18T08:20Z |

Not cached deliberately: the H.264 spec (ITU-T H.264 is not redistributable;
the handful of NAL-unit facts we rely on are documented inline in
`src/hflow/video.py`).
