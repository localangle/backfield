"""Compatibility import path; prefer ``backfield_stylebook.geocode_cache.sanity``."""

import backfield_stylebook.geocode_cache.sanity as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
