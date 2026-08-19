"""Gunicorn import target for hosted AIP."""

from .config import Config
from .web import create_app


application = create_app(config=Config.from_env())
