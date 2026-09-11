from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import open_session


def get_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    yield from open_session(settings.database_url)
