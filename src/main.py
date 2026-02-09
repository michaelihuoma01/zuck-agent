"""ZURK - Agent Command Center entry point."""

from src.api.app import create_app
from src.config import get_settings

# Create the application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
