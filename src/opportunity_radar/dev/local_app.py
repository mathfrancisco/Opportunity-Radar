"""Unauthenticated factory for local development and hermetic CI only."""

from fastapi import FastAPI

from opportunity_radar.presentation.http.app import create_development_app


def create_app() -> FastAPI:
    """Serve the explicit local development app, never the production factory."""
    return create_development_app()
