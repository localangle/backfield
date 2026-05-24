"""Compatibility import path; prefer ``backfield_stylebook.canonical.jurisdiction``."""

import backfield_stylebook.canonical.jurisdiction as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
