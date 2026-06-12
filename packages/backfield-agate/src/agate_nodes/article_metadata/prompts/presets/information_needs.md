### TASK: Classify the **Critical Information Need** of a local news article

Identify the article's **critical information need(s)** — the practical civic or community information need the story helps readers meet.

Critical information needs describe the kinds of information people require to navigate everyday life, participate in their communities, make decisions, stay safe, and understand local conditions.

Select **1 to 3 critical information needs maximum**.
Only assign multiple needs when the article clearly serves more than one major information need.
Be conservative: most stories should have **one** critical information need.

Critical information needs reflect **what public need the article serves**, not the article's subject label, format, popularity, timeliness, or geographic scope.

## Categories
- emergencies_risks
- health_welfare
- education
- transportation
- economic_opportunities
- environment
- civic_information
- political_information
- other

## Critical information need definitions

| Label | Definition | Key Signals |
|-------|------------|-------------|
| `emergencies_risks` | Information people need to prepare for, respond to, or recover from immediate or long-term risks. | Severe weather, fires, floods, crime threats, public safety alerts, disaster warnings |
| `health_welfare` | Information about physical health, mental health, public health, social services, care access, benefits, or basic well-being. | Hospitals, clinics, disease outbreaks, insurance, food assistance, shelter, child care |
| `education` | Information about schools, colleges, educational access, school quality, student outcomes, education policy, or choices for families and students. | K-12 schools, districts, colleges, school boards, curriculum, funding, enrollment |
| `transportation` | Information about how people move through the community, including systems, routes, costs, access, safety, and disruptions. | Roads, transit, traffic, construction, bike/pedestrian access, airports, rail, bus routes |
| `economic_opportunities` | Information about jobs, wages, business conditions, job training, entrepreneurship, household finances, or local economic opportunity. | Employment, layoffs, hiring, workforce training, small business help, wages, consumer costs |
| `environment` | Information about local environmental conditions, environmental risks, natural resources, climate impacts, or access to restoration and recreation. | Air and water quality, pollution, land conservation, climate change, parks, outdoor access |
| `civic_information` | Information people need to understand, access, or participate in community institutions, services, associations, and shared civic life. | Local institutions, public meetings, nonprofits, community groups, civic participation |
| `political_information` | Information about candidates, elected officials, campaigns, elections, voting, public policy, legislation, or government decisions affecting communities. | Elections, candidates, officeholders, ballot measures, laws, ordinances, governance |
| `other` | The article does not clearly serve one of the standard critical information needs. | Entertainment-only, lifestyle-only, unusual, or unclear public information need |

### Rules

- Select **only critical information needs that are core to the article's public value**.
- Assign **1 need** unless two or three clearly apply.
- Do **not** classify based only on a passing mention or newsroom beat.
- Choose the need the reader could reasonably act on, use, or understand better because of the article.
- Use `other` only when no category fits.

### Distinguishing guidance

- A city council story about budget, ordinance, election, or policy usually serves `political_information`.
- Public meeting access, services, neighborhood efforts, or local institutions may serve `civic_information`.
- Crime stories about safety threats, risk, response, or prevention serve `emergencies_risks`.
- School funding generally serves `education`; legislation-focused debate may also serve `political_information`.
- Housing rent burden, homelessness, or shelter access may serve `health_welfare`; jobs/income focus may serve `economic_opportunities`.
- Road closures or transit changes serve `transportation`; crashes or dangerous conditions may also serve `emergencies_risks`.
- Park, pollution, or climate stories usually serve `environment`.
- Restaurant reviews, arts previews, sports gamers, recipes, or entertainment features should be `other` unless they clearly serve a public information need above.

**Clarifying examples (not few-shot):**
- Tornado warning and shelter locations → `emergencies_risks`
- Local clinic closing → `health_welfare`
- School district changes attendance boundaries → `education`
- Bus route changes begin Monday → `transportation`
- New job training program for laid-off workers → `economic_opportunities`
- Report finds unsafe drinking water levels → `environment`
- Neighborhood association seeks volunteers for cleanup → `civic_information`
- County commission candidates debate tax proposal → `political_information`
- Restaurant opens downtown → `other`

### Few-shot examples

#### Example 1 — Political information
**Headline:** "City council approves $2.3B budget after 5–2 vote"

```json
[
  {
    "category": "political_information",
    "confidence": 0.95,
    "rationale": "The story helps residents understand a government decision and public policy affecting the community."
  }
]
```

#### Example 2 — Education and political information
**Headline:** "School board votes to close two elementary schools next year"

```json
[
  {
    "category": "education",
    "confidence": 0.94,
    "rationale": "The story provides information families need about local school access and district changes."
  },
  {
    "category": "political_information",
    "confidence": 0.82,
    "rationale": "The closures were decided through a public board vote with policy implications."
  }
]
```

#### Example 3 — Transportation
**Headline:** "Metro Transit will cut three bus routes starting in July"

```json
[
  {
    "category": "transportation",
    "confidence": 0.96,
    "rationale": "The story provides practical information about transit access, routes, and service changes."
  }
]
```

#### Example 4 — Emergencies and risks
**Headline:** "Officials order evacuations as wildfire spreads toward rural subdivision"

```json
[
  {
    "category": "emergencies_risks",
    "confidence": 0.98,
    "rationale": "The story provides urgent information residents need to respond to an immediate safety threat."
  }
]
```

#### Example 5 — Health and welfare
**Headline:** "County opens new walk-in mental health crisis center"

```json
[
  {
    "category": "health_welfare",
    "confidence": 0.96,
    "rationale": "The story helps residents understand and access a local health and social support service."
  }
]
```

#### Example 6 — Economic opportunities
**Headline:** "New manufacturing training program aims to connect workers with local jobs"

```json
[
  {
    "category": "economic_opportunities",
    "confidence": 0.95,
    "rationale": "The story provides information about job training and access to local employment opportunities."
  }
]
```

#### Example 7 — Environment and health welfare
**Headline:** "State finds elevated nitrate levels in private wells near farming region"

```json
[
  {
    "category": "environment",
    "confidence": 0.93,
    "rationale": "The story informs residents about local water quality and environmental health risks."
  },
  {
    "category": "health_welfare",
    "confidence": 0.80,
    "rationale": "The contamination may affect residents' health and well-being."
  }
]
```

#### Example 8 — Civic information
**Headline:** "Neighborhood group launches tool library for residents"

```json
[
  {
    "category": "civic_information",
    "confidence": 0.90,
    "rationale": "The story helps residents understand and access a community resource."
  }
]
```

#### Example 9 — Other
**Headline:** "Twins clinch division title with walk-off home run"

```json
[
  {
    "category": "other",
    "confidence": 0.85,
    "rationale": "The story is about a professional sports result and does not clearly serve one of the defined critical information needs."
  }
]
```

## Article text

{text}
