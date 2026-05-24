"""Compatibility import path; prefer ``backfield_stylebook.geocode_cache.resolve``."""

import backfield_stylebook.geocode_cache.resolve as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
