from backfield_db.text_sanitize import strip_nul_bytes, strip_nul_bytes_optional


def test_strip_nul_bytes_removes_nulls() -> None:
    assert strip_nul_bytes("Sky\x00s hot start.") == "Skys hot start."
    assert strip_nul_bytes("doesn\x00t") == "doesnt"
    assert strip_nul_bytes("problems\x00\x00\x00on offense") == "problemson offense"


def test_strip_nul_bytes_noop_without_nulls() -> None:
    assert strip_nul_bytes("Chicago Sky basketball") == "Chicago Sky basketball"


def test_strip_nul_bytes_optional() -> None:
    assert strip_nul_bytes_optional(None) is None
    assert strip_nul_bytes_optional("a\x00b") == "ab"
