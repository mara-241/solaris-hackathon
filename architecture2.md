# Solaris System Architecture (Level 2)

## Compact Diagram

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "fontFamily": "Inter, Arial",
    "fontSize": "12px",
    "primaryTextColor": "#e5e7eb",
    "lineColor": "#9ca3af",
    "tertiaryColor": "#111827",
    "clusterBkg": "#0f172a",
    "clusterBorder": "#334155"
  },
  "flowchart": {
    "nodeSpacing": 22,
    "rankSpacing": 24,
    "curve": "basis"
  }
}}%%
flowchart TB
    U[User]
    OC[OpenClaw]
    FE[Frontend]

    subgraph API[FastAPI]
      CHAT[POST /api/chat]
      EXEC[POST /openclaw/execute]
      LOC[GET/POST /api/locations]
    end

    subgraph CORE[Core Processing]
      ORCH[Orchestrator]
      AG[Perception + Spatial + Energy + Evidence]
    end

    DB[(SQLite/Postgres)]

    U --> OC
    U --> FE

    OC --> CHAT
    OC --> EXEC
    FE --> LOC
    FE --> CHAT

    CHAT --> ORCH
    EXEC --> ORCH
    ORCH --> AG
    AG --> ORCH

    ORCH --> DB
    LOC --> DB
    DB --> LOC

    LOC --> FE
    CHAT --> FE

    classDef actor fill:#1f2937,stroke:#6b7280,color:#f9fafb;
    classDef channel fill:#0b3b66,stroke:#38bdf8,color:#e0f2fe;
    classDef api fill:#3f2a18,stroke:#fb923c,color:#ffedd5;
    classDef core fill:#1f3b2c,stroke:#34d399,color:#ecfdf5;
    classDef data fill:#3b1f3a,stroke:#c084fc,color:#f3e8ff;

    class U actor;
    class OC,FE channel;
    class CHAT,EXEC,LOC api;
    class ORCH,AG core;
    class DB data;
```

## Flow

- User sends request from OpenClaw or frontend.
- FastAPI routes to chat/execute/location endpoints.
- Orchestrator runs agent workflow and returns analysis.
- Data is stored in DB and shown in frontend.
