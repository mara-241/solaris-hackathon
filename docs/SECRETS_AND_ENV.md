# Secrets and Environment

## Rule
Never commit tokens or secrets to the repository.

## GitHub token handling
Use an external secret manager (GitHub Secrets, 1Password, Vault, Doppler, etc.) and inject as env var only when needed.

Example (local shell):
```bash
export GITHUB_TOKEN="<token>"
```

## Storage backend selection
- Default: SQLite
- Postgres: set env vars and restart API

```bash
export SOLARIS_STORE=postgres
export DATABASE_URL="postgresql://user:pass@host:5432/solaris"
```

`apps/api/store.py` will auto-select `PostgresRunStore` when configured.
