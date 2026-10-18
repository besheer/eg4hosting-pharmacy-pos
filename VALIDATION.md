# v0.6.1 UI and branding validation

- Retained suite: 11 integration tests passed after UI shell changes.
- Shared shell JavaScript syntax and Python compilation passed.
- Launcher smoke: health 0.6.1, branded login, dashboard/POS/catalog/reports/inventory return 200 with the new shared shell.
- Sidebar uses one nonwrapping vertical layout with an independently scrolling menu.
- Windows splash implementation compiled; native Windows/Tk visual behavior and packaged EXE were not run here.
- New responsive layout, dark mode and mobile drawer have not been visually verified in a browser in this environment.
- Shared attendance conversation link could not be fetched; splash is a new design, not an exact copy.
- Data directory remains unchanged for upgrade compatibility.

# v0.6.0 validation — 2026-09-19

- Python compilation PASS.
- 11 integration tests PASS (including retained POS tests).
- CSV preview does not write products; confirmation writes once; replay does not duplicate records.
- Backup created before import. UTF-8 Arabic and leading-zero barcodes preserved in XLSX; Excel export round-trips through import.
- Duplicate rows, invalid prices, numeric Excel barcodes, formula cells, unsupported file types, stale previews rejected. Error CSV downloaded successfully.
- Exported XLSX text beginning with '=' remains literal text, not a formula.
- Sales fixture: net 180, tax 18, total 198, historical cost 120, gross profit 60. Current batch cost deliberately changed to 999; report still uses original cost.
- One-unit return in a later month: net -90, tax -9, total -99, cost reversal -60, gross profit -30. Combined product report: quantity 1, net 90, cost 60, profit 30.
- All 8 report types and their XLSX exports returned successfully; exported workbooks reopened and checked for data.
- Non-admin report account blocked from another branch and catalog import/export.
- v0.5.1 database upgraded to v0.6.0: existing product preserved; POS, catalog, reports and full print route returned 200.
- Local launcher smoke PASS: health=0.6.0, login, POS, catalog, Excel template, reports, print and Excel export.
- Retained POS tests: multi-line checkout, discounts/tax, split payment, idempotency, stock rollback, concurrent last-unit sale, partial refunds, branch permissions, Windows UTF-8 template reading and missing-template fallback.

## Limits
Windows EXE build/execution, Docker build, visual browser layout review, physical printing and native Excel application were not tested in this Linux environment. Excel file structure/content was checked using the application reader. No claims of production readiness, tax compliance, complete accounting, or completed branch replication. See README for report definitions and old-data limitations.
