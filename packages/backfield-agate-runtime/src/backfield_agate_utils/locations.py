"""Utilities for matching locations to Stylebook canonicals."""

import logging
import requests
from typing import Optional, Dict, Any


def match_canonical_location(
    name: str,
    base_url: str,
    project_slug: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
    service_token: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[Dict[str, Any]]:
    """
    Match a location name to a canonical StylebookLocation via stylebook-api /geo/match.

    Args:
        name: Location name to match (e.g., "Bridgeport, Chicago, IL")
        base_url: Base URL for Stylebook API
        project_slug: Project slug (required)
        city: Optional city filter for disambiguation
        state: Optional state filter for disambiguation
        service_token: Service API token for authentication
        timeout: Request timeout in seconds

    Returns:
        Dict with canonical location data (id, label, etc.), or None if no match or multiple matches
    """
    try:
        url = f"{base_url.rstrip('/')}/geo/match"
        params = {
            "project_slug": project_slug,
            "name": name,
        }
        if city:
            params["city"] = city
        if state:
            params["state"] = state

        headers = {}
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"

        logging.info(
            f"Stylebook canonical location match: name={name}, project_slug={project_slug}"
        )
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        result = response.json()

        if result.get("multiple_matches"):
            logging.info(
                f"Multiple canonical matches found for '{name}', leaving location as-is"
            )
            return None

        match_data = result.get("match")
        if match_data:
            # geo/match returns id as string; normalize to int for consistency
            raw_id = match_data.get("id")
            if raw_id is not None:
                try:
                    match_data = {**match_data, "id": int(raw_id)}
                except (ValueError, TypeError):
                    pass
            logging.info(
                f"Found canonical location match for '{name}': canonical_id={match_data.get('id')}"
            )
            return match_data
        else:
            logging.debug(f"No canonical location match found for '{name}'")
            return None

    except requests.Timeout:
        logging.warning(f"Canonical location match request timed out for '{name}'")
        return None
    except requests.RequestException as e:
        logging.warning(f"Canonical location match request failed for '{name}': {e}")
        return None
    except Exception as e:
        logging.error(f"Error matching canonical location '{name}': {e}")
        return None
