# NeoX Profile Payloads

This directory separates NeoX profile payload data by test intent.

- `minmax/`: success payloads used by official min/max readwrite create verification.
- `invalid/`: future negative payload cases with expected failure details.
- `observed/`: future live-device observations and known endpoint limits that are not official success data.

Keep success payloads out of `invalid/` and `observed/` so official create tests only load data expected to return `Success`.
