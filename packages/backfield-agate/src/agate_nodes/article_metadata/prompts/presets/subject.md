### TASK: Classify the **Subject** of a local news article

Identify the article's **primary subject areas** — what the story is fundamentally *about*.
Select **1 to 3 subjects maximum**.
Only assign multiple subjects when the article clearly covers more than one major domain.
Be conservative: most stories should have **one** subject.

Subjects reflect **what is being covered**, not the article's format, timeliness, or geographic scope.

## Categories
- local_government_politics
- state_government_politics
- global_national_politics
- courts_legal_system
- accountability_government_oversight
- public_safety_crime
- health_public_health
- weather_natural_hazards
- disaster_recovery
- roads_traffic
- transportation_transit
- housing_development
- land_use_zoning
- housing_affordability_homelessness
- real_estate_market
- climate_environment
- utilities_energy
- k12_education
- higher_education
- science_technology
- business_economy
- labor_workforce
- agriculture_rural
- immigration_demographics
- military_veterans
- consumer_affairs
- nonprofits_philanthropy
- media_journalism
- community_life
- religion_faith
- food_restaurants
- arts_culture
- animals_pets
- events_festivals
- travel
- outdoor_recreation
- pro_sports
- college_sports
- prep_youth_sports
- obituaries
- recipes
- other

## Subject definitions

### Government, Law & Politics
`local_government_politics`, `state_government_politics`, `global_national_politics`, `courts_legal_system`, `accountability_government_oversight`

### Public Services & Safety
`public_safety_crime`, `health_public_health`, `weather_natural_hazards`, `disaster_recovery`

### Infrastructure, Space & Environment
`roads_traffic`, `transportation_transit`, `housing_development`, `land_use_zoning`, `housing_affordability_homelessness`, `real_estate_market`, `climate_environment`, `utilities_energy`

### Economy, Education & Institutions
`k12_education`, `higher_education`, `science_technology`, `business_economy`, `labor_workforce`, `agriculture_rural`, `immigration_demographics`, `military_veterans`, `consumer_affairs`, `nonprofits_philanthropy`, `media_journalism`

### Community, Culture & Lifestyle
`community_life`, `religion_faith`, `food_restaurants`, `arts_culture`, `animals_pets`, `events_festivals`

### Travel & Recreation
`travel`, `outdoor_recreation`

### Sports
`pro_sports`, `college_sports`, `prep_youth_sports`

### Special Content
`obituaries`, `recipes`, `other`

### Rules

- Select **only subjects that are core to the article's focus**.
- Assign **1 subject** unless two or three clearly apply.
- Do **not** select broad categories unless supported by the story.
- When the story touches multiple areas, choose the **most central** domains.
- Use `other` only when no category fits.

**Clarifying examples (not few-shot):**
- Rent burden story → `housing_affordability_homelessness`
- New mall opening → `business_economy`
- City festival → `events_festivals`

### Few-shot examples

#### Example 1 — Single subject
**Headline:** "City council approves $2.3B budget after 5–2 vote"

```json
[
  {
    "category": "local_government_politics",
    "confidence": 0.95,
    "rationale": "The story is fundamentally about a local government budget decision."
  }
]
```

#### Example 2 — Two subjects
**Headline:** "Council vote on zoning change sparks debate over affordable housing"

```json
[
  {
    "category": "local_government_politics",
    "confidence": 0.90,
    "rationale": "A city council zoning vote is a core focus of the story."
  },
  {
    "category": "housing_affordability_homelessness",
    "confidence": 0.88,
    "rationale": "Affordable housing impacts are a major secondary theme."
  }
]
```

#### Example 3 — Single subject (sports)
**Headline:** "Twins clinch division title with walk-off home run"

```json
[
  {
    "category": "pro_sports",
    "confidence": 0.97,
    "rationale": "Professional sports game outcome is the central focus."
  }
]
```

## Article text

{text}
