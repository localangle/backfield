Given this description of a location: {address_text}

## Task

Estimate a plausible latitude, longitude, and search radius for this location.

## Required Output

Return only a JSON object with:
- **"latitude"**: Estimated latitude in decimal degrees
- **"longitude"**: Estimated longitude in decimal degrees  
- **"radius"**: Search radius in meters (should be appropriate for the type of location)

**Example:**
```json
{{
  "latitude": 44.9778, 
  "longitude": -93.265, 
  "radius": 50000
}}
```

## Radius Guidelines

Choose the radius based on the road type and context:

- **Specific streets in major cities** (e.g., "Broadway, New York"): 5000-10000 meters
- **Highways/interstates** (e.g., "I-35, Minneapolis"): 10000-20000 meters  
- **County roads in rural areas** (e.g., "County Road 15, Minnesota"): 15000-25000 meters
- **Main streets in small towns** (e.g., "Main St, Small Town"): 8000-15000 meters
- **City streets with neighborhood context** (e.g., "Lake St, Minneapolis"): 5000-10000 meters
- **Major thoroughfares** (e.g., "Hiawatha Ave, Minneapolis"): 8000-15000 meters

## Guidelines

- Smaller radius for precise urban streets
- Larger radius for rural/highway roads
- Base your estimate on the geographic context and typical road layouts in the area mentioned 