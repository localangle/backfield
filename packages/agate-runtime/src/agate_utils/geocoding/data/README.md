# Who's On First SQLite (optional)

Geocode enrichment (`wof.py`) can use a local copy of the Who's On First admin US SQLite database.

The file `whosonfirst-data-admin-us-latest.db` is **not** committed (GitHub file size limit). Download a release from the [Who's On First distribution](https://whosonfirst.org/download/) and place it in this directory, or set **`WOF_SQLITE_DB_PATH`** to an absolute path to the database file.

If the database is missing, WOF-backed helpers may raise `FileNotFoundError` or log warnings when those code paths run.
