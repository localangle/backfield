import os
import sqlite3
import logging
import json
import importlib
from typing import List, Dict, Any, Optional
from pathlib import Path

# Path to the Who's On First database (optional; see geocoding/data/README.md)
_DEFAULT_WOF = Path(__file__).parent / "data" / "whosonfirst-data-admin-us-latest.db"
WOF_DB_PATH = Path(os.environ.get("WOF_SQLITE_DB_PATH", str(_DEFAULT_WOF)))

def get_concordances_by_id(wof_id: str) -> Dict[str, str]:
    """
    Retrieve all concordance records for a given Who's On First ID.
    
    Args:
        wof_id (str): The Who's On First ID to look up
        
    Returns:
        Dict[str, str]: Dictionary mapping source systems to their IDs, e.g.:
            {
                "dbp:id": "85969169",
                "fct:id": "08c81220-8f76-11e1-848f-cfd5bf3ef515",
                "gn:id": "5037649.0",
                "wd:id": "Q36091",
                ...
            }
            
    Raises:
        FileNotFoundError: If the WOF database file doesn't exist
        sqlite3.Error: If there's an error querying the database
    """
    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")
    
    try:
        with sqlite3.connect(WOF_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()
            
            # Extract numeric ID from WOF ID (e.g., "whosonfirst:locality:101711873" -> "101711873")
            wof_id_numeric = wof_id.split(":")[-1]
            
            query = "SELECT other_source, other_id FROM concordances WHERE id = ?"
            cursor.execute(query, (wof_id_numeric,))
            
            rows = cursor.fetchall()
            concordances = {row['other_source']: row['other_id'] for row in rows}
            
            logging.info(f"Found {len(concordances)} concordances for WOF ID {wof_id}")
            return concordances
            
    except sqlite3.Error as e:
        logging.error(f"Database error querying concordances for ID {wof_id}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error querying concordances for ID {wof_id}: {e}")
        raise

def get_concordances_by_source_id(source: str, source_id: str) -> Dict[str, str]:
    """
    Retrieve all concordance records for a given source system and source ID.
    
    Args:
        source (str): The source system (e.g., 'gn', 'qs', 'osm', etc.)
        source_id (str): The ID in the source system
        
    Returns:
        Dict[str, str]: Dictionary mapping source systems to their IDs
        
    Raises:
        FileNotFoundError: If the WOF database file doesn't exist
        sqlite3.Error: If there's an error querying the database
    """
    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")
    
    try:
        with sqlite3.connect(WOF_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT other_source, other_id FROM concordances WHERE other_source = ? AND other_id = ?"
            cursor.execute(query, (source, source_id))
            
            rows = cursor.fetchall()
            concordances = {row['other_source']: row['other_id'] for row in rows}
            
            logging.info(f"Found {len(concordances)} concordances for {source}:{source_id}")
            return concordances
            
    except sqlite3.Error as e:
        logging.error(f"Database error querying concordances for {source}:{source_id}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error querying concordances for {source}:{source_id}: {e}")
        raise

def get_name_by_id(wof_id: str) -> str:
    """
    Retrieve the name for a given Who's On First ID.
    """
    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")
    
    try:
        with sqlite3.connect(WOF_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT name FROM spr WHERE id = ? AND is_current = 1"
            cursor.execute(query, (wof_id,))
            
            row = cursor.fetchone()
            return row['name']
    except sqlite3.Error as e:
        logging.error(f"Database error querying name for ID {wof_id}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error querying name for ID {wof_id}: {e}")
        raise

def get_bbox_by_id(wof_id: str) -> Dict[str, float]:
    """
    Retrieve the bounding box for a given Who's On First ID.
    """
    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")
    
    try:
        with sqlite3.connect(WOF_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT min_latitude, min_longitude, max_latitude, max_longitude FROM spr WHERE id = ? AND is_current = 1"
            cursor.execute(query, (wof_id,))
            
            row = cursor.fetchone()
            return [row['min_longitude'], row['min_latitude'], row['max_longitude'], row['max_latitude']]
    except sqlite3.Error as e:
        logging.error(f"Database error querying bounding box for ID {wof_id}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error querying bounding box for ID {wof_id}: {e}")
        raise

def get_geocode_by_id(wof_id: str) -> Dict[str, float]:
    """
    Retrieve the geocode object for a given Who's On First ID.
    """
    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")

    wof_id_numeric = wof_id.split(":")[-1]
    
    geocode = {
        "geocode": {
            "geocode_type": "wof",
            "result": {
                "id": wof_id,
                "formatted_address": get_name_by_id(wof_id_numeric),
                "geometry": {
                    "type": "Polygon",
                    "coordinates": get_bbox_by_id(wof_id_numeric)
                },
            }
        }
    }

    return geocode

def get_parents_by_coords(lat: float, lon: float, placetype: str) -> Dict[str, Dict[str, str]]:
    """
    Retrieve the parents for a given set of coordinates.
    Returns a structured format with placetype as keys and name/id as values.
    """
    logging.info(f"Getting parents for coordinates {lat}, {lon} with placetype {placetype}")

    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")

    try:
        with sqlite3.connect(WOF_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            placetype_filter = ""
            if placetype == 'state':
                return {}
            elif placetype == "county":
                placetype_filter = " AND placetype = 'region'"
            elif placetype == "city":
                placetype_filter = " AND placetype IN ('region', 'county')"
            elif placetype == "neighborhood":
                placetype_filter = " AND placetype IN ('region', 'county', 'locality')"
            else:
                placetype_filter = " AND placetype IN ('region', 'county', 'locality', 'neighbourhood')"

            query = """
            SELECT id, name, placetype
            FROM spr
            WHERE min_latitude <= ? AND max_latitude >= ? AND min_longitude <= ? AND max_longitude >= ? AND is_current = 1
            """
            if placetype_filter:
                query += placetype_filter

            cursor.execute(query, (lat, lat, lon, lon))
            candidate_rows = cursor.fetchall()

            filtered_rows: List[sqlite3.Row] = []

            for row in candidate_rows:
                if _point_within_feature(conn, row["id"], lon, lat):
                    filtered_rows.append(row)

    except sqlite3.Error as e:
        logging.error(f"Database error querying parents for coordinates {lat}, {lon}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error querying parents for coordinates {lat}, {lon}: {e}")
        raise

    parents: Dict[str, Dict[str, str]] = {}
    for row in filtered_rows:
        wof_id = f"whosonfirst:{row['placetype']}:{row['id']}"
        placetype_key = row['placetype']
        
        # Map WOF placetypes to our expected keys
        if placetype_key == 'region':
            key = 'state'
        elif placetype_key == 'county':
            key = 'county'
        elif placetype_key == 'locality':
            key = 'city'
        elif placetype_key == 'neighbourhood':
            key = 'neighborhood'
        else:
            key = placetype_key
            
        parents[key] = {
            "name": row['name'],
            "id": wof_id
        }

    logging.info(f"Found {len(parents)} parents for coordinates {lat}, {lon} with placetype {placetype}")

    return parents


def _point_within_feature(conn: sqlite3.Connection, wof_numeric_id: Any, lon: float, lat: float) -> bool:
    """Return True if the given point is within the feature's polygon geometry."""
    try:
        shapely_geometry = importlib.import_module("shapely.geometry")
        shapely_errors = importlib.import_module("shapely.errors")
        Point = getattr(shapely_geometry, "Point")
        shape = getattr(shapely_geometry, "shape")
        ShapelyError = getattr(shapely_errors, "ShapelyError")
    except ModuleNotFoundError:
        logging.warning("Shapely not available; skipping geometry containment test")
        return True

    try:
        cursor = conn.execute("SELECT body FROM geojson WHERE id = ?", (wof_numeric_id,))
        row = cursor.fetchone()
        if not row:
            return True  # fall back to bbox-only if geometry missing

        feature = json.loads(row["body"])
        geometry = feature.get("geometry") or feature
        shapely_geom = shape(geometry)
        point = Point(lon, lat)
        return shapely_geom.covers(point)
    except (json.JSONDecodeError, ShapelyError, TypeError, ValueError) as exc:
        logging.warning("Failed geometry check for WOF id %s: %s", wof_numeric_id, exc)
        return True  # do not exclude on parsing errors
    except sqlite3.Error as exc:
        logging.warning("Failed geometry lookup for WOF id %s: %s", wof_numeric_id, exc)
        return True

def get_id_by_coords(lat: float, lon: float, placetype: Optional[str]) -> Optional[str]:
    """
    Retrieve the Who's On First ID for a given set of coordinates.
    
    Returns None if placetype is not recognized or not provided.
    """
    if not placetype:
        return None
        
    logging.info(f"Getting ID for coordinates {lat}, {lon} with placetype {placetype}")
    
    if not WOF_DB_PATH.exists():
        raise FileNotFoundError(f"Who's On First database not found at {WOF_DB_PATH}")
    
    try:
        with sqlite3.connect(WOF_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            placetype_filter, id_prefix = "", ""
            if placetype == 'state':
                placetype_filter = " AND placetype = 'region'"
                id_prefix = "whosonfirst:region:"
            elif placetype == "county":
                placetype_filter = " AND placetype = 'county'"
                id_prefix = "whosonfirst:county:"
            elif placetype == "city":
                placetype_filter = " AND placetype = 'locality'"
                id_prefix = "whosonfirst:locality:"
            elif placetype == "neighborhood":
                placetype_filter = " AND placetype = 'neighbourhood'"
                id_prefix = "whosonfirst:neighbourhood:"
            else:
                # Return None when placetype is not recognized
                # The caller should handle this by using Nominatim place_id as fallback
                return None
            
            query = """
            SELECT id
            FROM spr
            WHERE min_latitude <= ? AND max_latitude >= ? AND min_longitude <= ? AND max_longitude >= ? AND is_current = 1
            """

            if placetype_filter:
                query += placetype_filter

            query += " ORDER BY id LIMIT 1"

            cursor.execute(query, (lat, lat, lon, lon))
            row = cursor.fetchone()
            return f"{id_prefix}{row['id']}"
    except sqlite3.Error as e:
        logging.error(f"Database error querying ID for coordinates {lat}, {lon}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error querying ID for coordinates {lat}, {lon}: {e}")
        raise