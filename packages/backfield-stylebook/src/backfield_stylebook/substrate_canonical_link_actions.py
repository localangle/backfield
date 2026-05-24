"""Compatibility import path; prefer ``backfield_stylebook.canonical.substrate_link_actions``."""

import backfield_stylebook.canonical.substrate_link_actions as _impl

globals().update({name: value for name, value in vars(_impl).items() if not name.startswith("__")})
