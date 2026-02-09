# Agent Command Center

## Project Overview
A centralized orchestration system for managing Claude Code sessions remotely.

Project is calleed ZURK

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0, aiosqlite
- **Agent SDK**: claude-agent-sdk (official Anthropic SDK)
- **Frontend**: React, TypeScript, Tailwind CSS (Phase 3)
- **Database**: SQLite (async)

## Architecture
See AGENT_COMMAND_CENTER_PROJECT.md for complete specification.

## Code Style
- Use type hints everywhere
- Async/await for all I/O
- Pydantic for validation
- pytest for testing
- Black for formatting
- Ruff for linting

## Key Files
- `AGENT_COMMAND_CENTER_PROJECT.md` - Complete project specification
- `src/core/agent_runtime.py` - Claude SDK wrapper (critical)
- `src/api/` - FastAPI routes
- `src/models/` - SQLAlchemy models

## Commands
```bash
# Run development server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v

# Format code
black src/ tests/ && ruff check src/ tests/ --fix
```

## Current Focus
Check Implementation Checklist in AGENT_COMMAND_CENTER_PROJECT.md

## Do Not
- Change the architecture without updating the project doc
- Add dependencies without documenting in pyproject.toml
- Skip tests for core business logic
- Use sync I/O in async contexts

But feel free to suggest better, simplified, easier logic or process library if the current instructions are too rigid or over engineered.




