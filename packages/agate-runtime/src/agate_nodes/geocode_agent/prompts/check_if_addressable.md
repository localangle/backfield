# Addressability Check

You will be given a string with the name of a place. Determine if it is likely a building or landmark with a physical street address that could be found by searching the internet.

## Addressable Locations

This might include:
- **Businesses**
- **Landmarks**
- **Buildings**
- **Schools**
- **Parks**
- **Specific facilities or venues**

## Non-Addressable Locations

This would NOT include:
- General regions or areas
- Cities, counties or administrative divisions
- Natural features like lakes or forests
- Abstract concepts or non-physical locations

## Special Case

If the string already contains a full street address including a street number, city and state (such as "123 Fake St., Monticello, MN"), return "has address".

## Input

**Location:** {location}

## Response

Return ONLY one of these three values:
- `addressable` - if the place likely has a physical address
- `not addressable` - if the place doesn't have a physical address
- `has address` - if the string already contains a full address

