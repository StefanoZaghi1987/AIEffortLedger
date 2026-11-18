---
status: accepted
date: 2026-11-18
---

# The store is private, outside project repositories by default, and holds no content

Each person has one store in the user data folder of the operating system; a setting can move it anywhere, also into a
repository, with or without `.gitignore`, if the person chooses so. The store holds times, counters, token usage, and
metadata, never the text of prompts, responses, or code; session titles enter only with explicit consent. Team
reporting uses team exports that the person reviews before sharing. Shared configuration (project rules, milestones,
releases, price tables) can live in a project repository because it holds no personal data.

## Considered Options

- **Data file committed in the project repository**: rejected; in a repository with several people it publishes the
  working pattern of each person, and it couples the measurement to git.
- **Central server or telemetry backend**: possible later for a team, but it is infrastructure that must run and it
  centralizes personal data by default.
