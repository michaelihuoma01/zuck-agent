"""Health check routes."""

import subprocess

from fastapi import APIRouter

from src.api.schemas import HealthResponse, AgentHealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint.

    Returns the service status and version.
    """
    return HealthResponse(status="healthy", version="0.1.0")


@router.get("/agent", response_model=AgentHealthResponse)
async def agent_health_check() -> AgentHealthResponse:
    """Check Claude SDK/CLI connectivity.

    Verifies that the Claude Code CLI is installed and accessible.
    This doesn't make an API call, just checks CLI availability.
    """
    try:
        # Check if claude CLI is available
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            return AgentHealthResponse(
                status="healthy",
                cli_available=True,
            )
        else:
            return AgentHealthResponse(
                status="degraded",
                cli_available=False,
                error=f"CLI returned non-zero exit code: {result.returncode}",
            )

    except FileNotFoundError:
        return AgentHealthResponse(
            status="unhealthy",
            cli_available=False,
            error="Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
        )
    except subprocess.TimeoutExpired:
        return AgentHealthResponse(
            status="unhealthy",
            cli_available=False,
            error="CLI check timed out",
        )
    except Exception as e:
        return AgentHealthResponse(
            status="unhealthy",
            cli_available=False,
            error=str(e),
        )
