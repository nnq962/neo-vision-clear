"""FastAPI server cung cấp snapshot lối đi cho các hệ thống bên ngoài."""

from server.app import create_app

__all__ = ["create_app"]
