# NeoX Config Data

NeoX config test data is grouped by feature area. Active files in these folders are allowed to feed official pytest cases and local contract checks.

- `ge/`: GE interface official payload config. Max variants, negative cases, and show-command references are kept in the same GE config file.
- `nni/`: NNI interface official payload config. Min/max cases are kept in the same NNI config file.
- `vlan/`: VLAN official payload config. Min/max and negative cases are kept in the same VLAN config file.
- `ont/`: ONT official payload config. Min/max, dynamic max, and negative cases are kept in the same ONT config file.
- `profiles/`: NeoX profile min/max payloads, invalid cases, CLI verify mappings, and follow-up notes.
- `reference/`: Swagger/User Guide derived references and the NeoX feature test data index.

Keep only official REST payloads in the matching feature folder. Do not keep exploratory probe output under `configs/neox_config/` after the confirmed values are promoted into official min/max, variant, or invalid-case config.

