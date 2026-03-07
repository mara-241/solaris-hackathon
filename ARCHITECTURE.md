# Solaris System Architecture

## Demo Diagram

```mermaid
flowchart LR
    U[User] --> OC[OpenClaw]
    U --> FE[Frontend]
    OC --> API[FastAPI Backend]
    FE --> API
    API --> AG[AI Agents]
    AG --> API
    API --> DB[(Database)]
    DB --> API
    API --> FE
```

## Demo Flow

- User asks from OpenClaw or frontend.
- Backend runs agents and creates analysis output.
- Output is stored in database.
- Frontend reads and displays saved results.
