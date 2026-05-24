"""Compatibility import path; prefer ``backfield_stylebook.canonical.link``."""

import backfield_stylebook.canonical.link as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
