### TASK: Classify the **User Need** of a local news article

Identify the article's **primary user need** — the reader motivation or audience need the story is mainly designed to satisfy.

User need describes **why a reader would seek out or value this story**, not the article's subject, format, timeliness, or geographic scope.

Choose **one** user need — the single **dominant** need the article serves.

## Categories
- update_me
- explain_it_to_me
- help_me_act
- hold_power_to_account
- show_me_the_community
- move_me
- entertain_me
- catch_me_up
- other

## User need definitions

| Label | Definition | Key Signals |
|-------|------------|-------------|
| `update_me` | Provides timely information about what happened, what changed, or what was announced. | Breaking news, votes, incidents, decisions, results, announcements |
| `explain_it_to_me` | Helps the reader understand what something means, how it works, why it matters, or what context is needed. | Explainers, analysis, background, causes, consequences, policy mechanics |
| `help_me_act` | Gives practical information to make a decision, solve a problem, access a resource, or take action. | How-to guidance, deadlines, eligibility, routes, schedules, safety steps, voting info |
| `hold_power_to_account` | Investigates, scrutinizes, or challenges people, institutions, systems, or decisions with power over public life. | Watchdog reporting, investigations, wrongdoing, failures, inequity, broken systems |
| `show_me_the_community` | Helps the reader understand the people, places, institutions, traditions, and shared life of a community. | Neighborhood life, local identity, civic groups, community rituals, belonging |
| `move_me` | Creates emotional connection through human experience, narrative, surprise, grief, joy, resilience, or meaning. | Human-interest storytelling, personal journeys, emotional scenes, lived experience |
| `entertain_me` | Gives enjoyment, diversion, recommendations, cultural discovery, or something interesting to talk about. | Sports, arts, food, reviews, events, things to do, lifestyle, leisure |
| `catch_me_up` | Orients the reader within an ongoing story, controversy, process, campaign, trial, project, or public conversation. | Recaps, follow-ups, "what we know," timelines, status checks, ongoing developments |
| `other` | The article does not clearly serve one of the standard user needs. | Unusual, hybrid, unclear, or primarily administrative content |

### Rules

- Select **only one** user need — the **dominant** audience motivation.
- Do **not** classify based only on the article's topic or format.
- Ask: **What reader need is this story mainly satisfying?**
- New event or decision → `update_me`.
- Explains context, causes, implications, or how something works → `explain_it_to_me`.
- Practical instructions or usable information → `help_me_act`.
- Exposes wrongdoing or scrutinizes power → `hold_power_to_account`.
- Local people, places, institutions, or community life → `show_me_the_community`.
- Emotional connection through lived experience → `move_me`.
- Enjoyment, recommendations, or diversion → `entertain_me`.
- Recap or status of an ongoing story → `catch_me_up`.
- No clear fit → `other`.

### Distinguishing guidance

- `update_me` vs. `catch_me_up`: New development → `update_me`. Recap, status check, or orientation to ongoing issue → `catch_me_up`.
- `update_me` vs. `explain_it_to_me`: Knowing what happened → `update_me`. Understanding meaning, context, or consequences → `explain_it_to_me`.
- `explain_it_to_me` vs. `help_me_act`: Learning how or why → `explain_it_to_me`. Taking a specific action → `help_me_act`.
- `hold_power_to_account` vs. `explain_it_to_me`: Scrutiny or investigation → `hold_power_to_account`. Understanding a system or issue → `explain_it_to_me`.
- `show_me_the_community` vs. `move_me`: Local identity and civic texture → `show_me_the_community`. Emotional narrative → `move_me`.
- `move_me` vs. `entertain_me`: Emotional resonance → `move_me`. Enjoyment or diversion → `entertain_me`.
- `entertain_me` vs. `help_me_act`: "Things to do" roundups are usually `entertain_me` unless practical action is the central purpose.

**Clarifying examples (not few-shot):**
- City council approves budget → `update_me`
- How the school funding formula works → `explain_it_to_me`
- Where to find cooling centers during a heat wave → `help_me_act`
- Investigation finds county failed to inspect rental units → `hold_power_to_account`
- Inside the neighborhood festival that has lasted 100 years → `show_me_the_community`
- Family rebuilds after tornado destroys their home → `move_me`
- 10 restaurants to try this summer → `entertain_me`
- What to know as the corruption trial enters week three → `catch_me_up`

### Few-shot examples

#### Example 1 — Update me
**Headline:** "City council approves $2.3B budget after 5–2 vote"

```json
{
  "category": "update_me",
  "confidence": 0.95,
  "rationale": "The story's main value is timely information about a local government decision."
}
```

#### Example 2 — Explain it to me
**Headline:** "How Minnesota's new school funding formula works"

```json
{
  "category": "explain_it_to_me",
  "confidence": 0.96,
  "rationale": "The story helps readers understand how a complex policy functions and why it matters."
}
```

#### Example 3 — Help me act
**Headline:** "How to apply for property tax relief before the deadline"

```json
{
  "category": "help_me_act",
  "confidence": 0.97,
  "rationale": "The story gives readers practical steps they can use to access a public benefit."
}
```

#### Example 4 — Hold power to account
**Headline:** "Audit finds city ignored years of complaints about unsafe apartments"

```json
{
  "category": "hold_power_to_account",
  "confidence": 0.96,
  "rationale": "The story scrutinizes government failures and accountability for unsafe housing conditions."
}
```

#### Example 5 — Show me the community
**Headline:** "At a century-old church supper, a town keeps its traditions alive"

```json
{
  "category": "show_me_the_community",
  "confidence": 0.92,
  "rationale": "The story helps readers understand a local tradition and the community built around it."
}
```

#### Example 6 — Move me
**Headline:** "After losing his wife, a retired teacher finds purpose mentoring young readers"

```json
{
  "category": "move_me",
  "confidence": 0.94,
  "rationale": "The story is centered on emotional connection, personal loss, resilience, and meaning."
}
```

#### Example 7 — Entertain me
**Headline:** "10 things to do around the metro this weekend"

```json
{
  "category": "entertain_me",
  "confidence": 0.97,
  "rationale": "The story provides leisure recommendations and diversion."
}
```

#### Example 8 — Catch me up
**Headline:** "What to know as the light rail extension faces another delay"

```json
{
  "category": "catch_me_up",
  "confidence": 0.90,
  "rationale": "The story orients readers to the current status of an ongoing public project."
}
```

#### Example 9 — Other
**Headline:** "Editor's note: How we corrected yesterday's newsletter"

```json
{
  "category": "other",
  "confidence": 0.75,
  "rationale": "The story is primarily administrative and does not clearly serve one of the defined user needs."
}
```

## Article text

{text}
