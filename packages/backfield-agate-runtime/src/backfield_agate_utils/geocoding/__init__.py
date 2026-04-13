"""
Geocoding tools package.

Provides geocoding and geometry helpers. Import submodules directly so that
code needing only geo_h3 (e.g. stylebook-canonicalization) does not pull in
nominatim's dependency on requests.

- backfield_agate_utils.geocoding.geo_h3 — H3 geometry (lat_lon_from_geometry_json, h3_cell_from_geometry)
- backfield_agate_utils.geocoding.nominatim — NominatimGeocoder, geocode_address (requires requests)
- backfield_agate_utils.geocoding.geocoding_types — GeocodingResult
"""
