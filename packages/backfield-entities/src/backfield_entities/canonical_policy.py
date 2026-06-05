"""Compatibility import path; prefer ``backfield_stylebook.entities.location.policy``."""

import backfield_stylebook.entities.location.policy as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
