# Storage migration context

The service writes production billing records to the old store. Reads must remain available throughout migration. A sampled shadow comparison can validate row counts and values. The old path can remain writable until cutover. Backfill and cutover affect shared production data and require an owner-approved rollback plan.
