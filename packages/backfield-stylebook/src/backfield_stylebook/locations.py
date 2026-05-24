"""Compatibility import path; prefer ``backfield_stylebook.entities.location.persist``."""

import backfield_stylebook.entities.location.persist as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
