"""Utilities for matching people to Stylebook canonicals."""

import logging
import requests
from typing import Optional, Dict, Any

def match_canonical_person(
    name: str,
    base_url: str,
    project_slug: str,
    service_token: Optional[str] = None,
    timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """
    Match a person name to a canonical StylebookPerson.
    
    Args:
        name: Person name to match (full name)
        base_url: Base URL for Stylebook API
        project_slug: Project slug (required)
        service_token: Service API token for authentication
        timeout: Request timeout in seconds
        
    Returns:
        Dict with canonical person data, or None if no match or multiple matches
    """
    try:
        url = f"{base_url.rstrip('/')}/people/match"
        params = {
            "project_slug": project_slug,
            "name": name
        }
        
        headers = {}
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"
        
        logging.info(f"Stylebook canonical person match: name={name}, project_slug={project_slug}")
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        
        # Check if there are multiple matches - if so, return None to leave person as-is
        if result.get("multiple_matches"):
            logging.info(f"Multiple canonical matches found for '{name}', leaving person as-is")
            return None
        
        if result.get("match"):
            logging.info(f"Found canonical person match for '{name}': canonical_id={result['match'].get('id')}")
            return result.get("match")
        else:
            logging.debug(f"No canonical person match found for '{name}'")
            return None
            
    except requests.Timeout:
        logging.warning(f"Canonical person match request timed out for '{name}'")
        return None
    except requests.RequestException as e:
        logging.warning(f"Canonical person match request failed for '{name}': {e}")
        return None
    except Exception as e:
        logging.error(f"Error matching canonical person '{name}': {e}")
        return None
