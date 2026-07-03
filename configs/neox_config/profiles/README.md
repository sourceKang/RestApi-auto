# NeoX Profile Payloads

This directory keeps official NeoX profile readwrite data by profile type.

- `minmax/`: one JSON file per profile type. Each file contains `min`, `max`, `cli_verify`, and active `negative_cases` for that profile.

Do not reintroduce root-level aggregate profile catalogs or a separate invalid-cases folder. Official profile tests should load profile data through `services.neox_config.service` helpers.