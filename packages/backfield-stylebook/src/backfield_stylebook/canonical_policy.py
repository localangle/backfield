"""Compatibility import path; prefer ``backfield_stylebook.canonical.policy``."""

import backfield_stylebook.canonical.policy as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
