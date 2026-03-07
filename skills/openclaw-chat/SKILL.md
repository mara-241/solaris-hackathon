---
name: openclaw_chat
description: Execute Solaris workflow by sending user input to POST http://localhost:8000/api/chat, preserving thread history, and waiting for long-running backend completion.
---

# OpenClaw Chat Skill

## Use when
Use this as the default Solaris execution path for user prompts.

## Base URL
- `http://localhost:8000`
- Do not use `127.0.0.1`, `0.0.0.0`, or any remote host in this skill.

## Endpoint (single source of truth)
- `POST /api/chat` on base URL `http://localhost:8000`
- Final URL: `http://localhost:8000/api/chat`

## Required execution workflow
1. Accept user input text.
2. Build request body with `message`, stable `thread_id`, and full `history`.
3. Send request to `POST http://localhost:8000/api/chat`.
4. Wait for backend completion. This backend can take multiple minutes.
5. Use response payload as final output (`messages`, `history`, `run_id`, `loc_id`, `satellite`).
6. Replace local history with returned `history`.

## Request payload
Send this shape:
```json
{
  "message": "Analyze solar energy demand for Nairobi for 150 households",
  "thread_id": "session-id",
  "history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

Optional fields accepted by backend:
- `lat`, `lon`, `households`, `horizon_days`, `usage_profile`

If coordinates are unknown, omit `lat`/`lon` instead of forcing `0,0`.

## Headers
- `Content-Type: application/json`
- `x-api-key: <SOLARIS_API_TOKEN>` (if auth enabled)

## Timeout and retries
- Treat `/api/chat` as long-running.
- Use request timeout of at least `300s` before declaring failure.
- Do not switch to local/synthetic analysis because of slow response.
- Retry only for network/transport errors, not for successful long-running requests.

## Response fields to use
- `messages` (assistant completion text)
- `history` (normalized conversation history)
- `run_id`, `loc_id` (only when analysis is triggered)
- `satellite` (preview/NDVI/NDWI payload)

## Runtime behavior rules
1. Always call only `/api/chat` for prompt handling in this skill.
2. Keep a stable `thread_id` per conversation.
3. Send full `history` each turn; then replace local history with server-returned `history`.
4. Pass user location as text in `message`; backend resolves coordinates/geocoding.
5. Never fabricate `run_id`, `loc_id`, coordinates, or satellite fields.
6. Never replace backend workflow with offline estimates, synthetic CSV generation, or local fallback logic.

## Analysis trigger guidance
The backend only persists a run when the prompt looks like an energy analysis request.
Include:
1. An energy term: `energy|power|solar|demand|usage|load|forecast|optimiz|size`
2. An action term: `analy|plan|generate|run|estimate|calculate|design`
3. A location phrase, usually with `for|in|at|near`

Working example:
- `Analyze solar energy demand for Nairobi for 150 households`

## Failure handling
1. Non-2xx: return backend `detail` exactly.
2. `run_id` missing: report that analysis was not triggered or location could not be resolved.
3. If `history` is missing in response, keep prior history and append current turn safely.
