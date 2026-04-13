# tools/geocoding/h3.py

def h3_cell(lat: float, lon: float, res: int = 12) -> str:
    """
    Return the H3 cell ID (hex string) for a given latitude/longitude at the specified resolution.

    Args:
        lat: latitude in degrees (-90..90)
        lon: longitude in degrees (-180..180)
        res: H3 resolution (0..15). Higher = finer cells. Common: 9 (~174m), 12 (~9m).

    Returns:
        H3 cell ID as a 15/16-character hex string.

    Raises:
        ValueError: if inputs are out of range.
        ImportError: if the 'h3' package isn't installed.
    """
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("lat must be [-90,90], lon must be [-180,180].")
    if not (0 <= res <= 15):
        raise ValueError("H3 resolution must be in [0, 15].")

    # Try H3 v4 first
    try:
        from h3 import latlng_to_cell  # type: ignore
        return latlng_to_cell(lat, lon, res)
    except ImportError:
        # Fall back to H3 v3 API
        try:
            import h3  # type: ignore
            return h3.geo_to_h3(lat, lon, res)
        except ImportError as e:
            raise ImportError("Please install H3: pip install h3") from e