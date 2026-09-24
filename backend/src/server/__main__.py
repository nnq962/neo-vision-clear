"""Entry point chạy FastAPI server bằng Uvicorn."""

import uvicorn

from server.app import create_app
from server.settings import ServerSettings


# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Đọc cấu hình môi trường và chạy một Uvicorn worker local."""
    # Một process chỉ nên sở hữu một camera/model, vì vậy không bật nhiều worker.
    settings = ServerSettings.from_env()
    settings.validate()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
    )


if __name__ == "__main__":
    main()
