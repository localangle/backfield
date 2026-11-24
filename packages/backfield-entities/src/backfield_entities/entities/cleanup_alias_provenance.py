"""The alias provenance for names the cleanup API adds (aliases, and old labels kept on an edit).

It is listed with the trusted provenances for each entity kind, so a name a client added counts as
an editor-approved alias in link checks. Locations and people list it among cleanup decisions;
organizations only trust editorial provenance, so it is listed there.
"""

CLEANUP_API_ALIAS_PROVENANCE = "stylebook_cleanup_api"
