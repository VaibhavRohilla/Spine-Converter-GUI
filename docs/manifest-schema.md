# Asset manifest schema 1

The deterministic JSON manifest has `schema_version`, `source`, sorted `assets`, `bundles`, `dependencies`, `diagnostics`, summary counts, and `ok`. Assets retain source-relative POSIX paths, typed classification, sizes and parser metadata. Dependencies retain requested and resolved paths and resolution status. Diagnostic `code` values are stable machine keys; severity is info, warning, error, or blocker. No conversion or runtime certification is represented by `ok`.
