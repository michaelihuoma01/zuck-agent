# Live Preview — Implementation Contract

> This file is the single source of truth for the Live Preview feature implementation.
> All agents (backend, frontend, test) read this file to stay in sync.

## Shared API Contract

### New Project Model Fields

```
dev_command   TEXT nullable   — e.g., "npm run dev" (auto-detected or user override)
dev_port      INT  nullable   — e.g., 5173 (auto-detected or user override)
```

These are added to:
- SQLAlchemy model: `src/models/project.py`
- Pydantic schemas: `ProjectCreate`, `ProjectUpdate`, `ProjectResponse` in `src/api/schemas.py`
- TypeScript interface: `Project`, `ProjectCreate`, `ProjectUpdate` in `frontend/src/api/types.ts`

### Detection Logic

`src/utils/project_detector.py` — single function:

```python
def detect_project_type(project_path: str) -> tuple[str | None, int | None, str | None]:
    """Returns (dev_command, dev_port, project_type) or (None, None, None)."""
```

Detection priority (reads `package.json` → `scripts.dev` + `dependencies`):
1. Vite: `"dev": "vite..."` → `("npm run dev -- --host 0.0.0.0", 5173, "vite")`
2. Next.js: `"next" in deps` → `("npm run dev -- -H 0.0.0.0", 3000, "nextjs")`
3. CRA: `"react-scripts" in deps` → `("npm start", 3000, "cra")` (CRA uses HOST=0.0.0.0 env var)
4. Nuxt: `"nuxt" in deps` → `("npm run dev -- --host 0.0.0.0", 3000, "nuxt")`
5. Generic npm with dev script → `("npm run dev", 3000, "node")`
6. Python Flask: `app.py` or `wsgi.py` exists → `("flask run --host 0.0.0.0", 5000, "flask")`
7. Python Django: `manage.py` exists → `("python manage.py runserver 0.0.0.0:8001", 8001, "django")` (port 8001 to avoid ZURK conflict)
8. No match → `(None, None, None)`

CRITICAL: All commands must bind to `0.0.0.0` (not localhost) for network accessibility.
CRA is special: uses `HOST=0.0.0.0` environment variable, not CLI flag.

### PreviewManager Service

`src/services/preview_manager.py`

```python
class PreviewManager:
    """Manages dev server subprocesses for project previews."""

    # In-memory tracking
    _processes: dict[str, ProcessInfo]  # project_id → ProcessInfo

    # PID file directory
    PID_DIR = Path("data/previews")

    async def start_preview(self, project: Project) -> PreviewStatus
    async def stop_preview(self, project_id: str) -> PreviewStatus
    def get_status(self, project_id: str) -> PreviewStatus
    def detect_running(self, port: int) -> bool
    async def cleanup_all(self) -> None  # Called on shutdown
    def _recover_orphans(self) -> None   # Called on startup
    def _get_tailscale_ip(self) -> str | None
    def _get_lan_ip(self) -> str | None
    def _build_url(self, port: int) -> str

@dataclass
class ProcessInfo:
    pid: int
    port: int
    project_id: str
    project_path: str
    started_at: datetime
    process: subprocess.Popen | None  # None if recovered from PID file

@dataclass
class PreviewStatus:
    running: bool
    url: str | None = None
    port: int | None = None
    pid: int | None = None
    uptime_seconds: int | None = None
    project_type: str | None = None
    error: str | None = None
```

Singleton pattern: Same as ApprovalHandler — module-level `_preview_manager` with asyncio.Lock.

### API Endpoints

All under existing `/projects` router in `src/api/routes/projects.py`:

```
POST /projects/{project_id}/preview/start
  Request: empty body (project has dev_command stored)
  Response 200: PreviewStatusResponse
  Response 400: {"detail": "No dev_command configured for this project"}
  Response 409: {"detail": "Preview already running for this project"}

POST /projects/{project_id}/preview/stop
  Request: empty body
  Response 200: PreviewStatusResponse
  Response 404: {"detail": "No preview running for this project"}

GET /projects/{project_id}/preview/status
  Response 200: PreviewStatusResponse
```

### Pydantic Schema

```python
class PreviewStatusResponse(BaseModel):
    running: bool
    url: str | None = None
    port: int | None = None
    pid: int | None = None
    uptime_seconds: int | None = None
    project_type: str | None = None
    error: str | None = None
```

### TypeScript Types

```typescript
// Add to Project interface
interface Project {
  // ... existing fields ...
  dev_command: string | null
  dev_port: number | null
}

// Add to ProjectCreate (optional)
interface ProjectCreate {
  // ... existing fields ...
  dev_command?: string | null
  dev_port?: number | null
}

// Add to ProjectUpdate (optional)
interface ProjectUpdate {
  // ... existing fields ...
  dev_command?: string | null
  dev_port?: number | null
}

// New type
interface PreviewStatus {
  running: boolean
  url: string | null
  port: number | null
  pid: number | null
  uptime_seconds: number | null
  project_type: string | null
  error: string | null
}
```

### API Client Methods

```typescript
// Add to projects object in client.ts
preview: {
  start: (projectId: string) => request<PreviewStatus>(`/projects/${projectId}/preview/start`, { method: 'POST', body: '{}' }),
  stop: (projectId: string) => request<PreviewStatus>(`/projects/${projectId}/preview/stop`, { method: 'POST', body: '{}' }),
  status: (projectId: string) => request<PreviewStatus>(`/projects/${projectId}/preview/status`),
}
```

### React Hook

`frontend/src/hooks/usePreview.ts`

```typescript
export function usePreview(projectId: string) → {
  status: PreviewStatus | undefined
  isLoading: boolean
  start: UseMutationResult
  stop: UseMutationResult
}
```

Query key: `['preview', projectId]`
Polling: every 5s when `status.running === true`, else false
Mutations invalidate `['preview', projectId]` on success

### React Component

`frontend/src/components/common/PreviewButton.tsx`

```typescript
interface PreviewButtonProps {
  projectId: string
  devCommand: string | null  // null = not configured
  size?: 'sm' | 'md'
}

export default function PreviewButton({ projectId, devCommand, size = 'md' }: PreviewButtonProps)
```

Renders:
- If `devCommand` is null: nothing (or disabled "No preview available" text)
- If not running: "Start Preview" button (primary variant)
- If running: green dot + clickable URL link + "Stop" button (ghost/danger variant)
- Loading spinner during start/stop transitions

### Placement

1. **ProjectDetailPage**: In the header section, next to "New Session" button
2. **SessionPage**: In the header bar, next to the StatusPill/cancel button

### Database Migration

Since ZURK doesn't use Alembic, add columns via SQL in the lifespan startup:

```python
# In src/api/app.py lifespan, after init_db():
await _run_migrations(engine)

async def _run_migrations(engine):
    """Add new columns if they don't exist (idempotent)."""
    async with engine.begin() as conn:
        # Check if columns exist
        result = await conn.execute(text("PRAGMA table_info(projects)"))
        columns = {row[1] for row in result.fetchall()}
        if "dev_command" not in columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN dev_command TEXT"))
        if "dev_port" not in columns:
            await conn.execute(text("ALTER TABLE projects ADD COLUMN dev_port INTEGER"))
```

### App Lifespan Changes

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging(debug=get_settings().debug)
    await init_db()
    await _run_migrations(engine)      # NEW: add preview columns
    preview_mgr = get_preview_manager()
    preview_mgr._recover_orphans()     # NEW: recover orphaned processes
    yield
    # Shutdown
    preview_mgr = get_preview_manager()
    await preview_mgr.cleanup_all()    # NEW: kill all dev servers
    reset_agent_runtime()
    await close_db()
```

### Security Constraints

1. Use `shlex.split(dev_command)` + `subprocess.Popen(args, shell=False)` — never `shell=True`
2. For CRA: pass `env={**os.environ, "HOST": "0.0.0.0"}` instead of shell command
3. Validate `dev_port` is in range 1024-65535 (no privileged ports)
4. Don't proxy arbitrary ports — only serve URLs for ports ZURK started
5. PID files prevent zombie processes across restarts

### Test Requirements

1. `tests/test_project_detector.py` — unit tests for detection logic
   - Test each framework detection (mock package.json contents)
   - Test fallback (no package.json)
   - Test user override precedence

2. `tests/test_preview_manager.py` — unit tests for service
   - Test start/stop lifecycle (mock subprocess.Popen)
   - Test PID file write/read/cleanup
   - Test port conflict detection (mock socket)
   - Test orphan recovery
   - Test cleanup_all

3. `tests/test_api/test_projects.py` — add API endpoint tests
   - Test POST /preview/start (success, no dev_command, already running)
   - Test POST /preview/stop (success, not running)
   - Test GET /preview/status (running, not running)
   - Test project CRUD with dev_command/dev_port fields
