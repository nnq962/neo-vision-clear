"""CLI khởi động aggregator bằng Uvicorn."""

import uvicorn

from neo_vision_clear_aggregator.app import create_app
from neo_vision_clear_aggregator.settings import AggregatorSettings


def main() -> None:
    """Đọc settings và chạy một process Uvicorn."""
    settings = AggregatorSettings.from_env()
    settings.validate()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
