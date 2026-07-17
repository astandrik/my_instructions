# Test conventions

Behavior crossing the adapter boundary belongs in `tests/integration/`. Do not use unit snapshots for adapter behavior because they bypass serialization and ordering.
