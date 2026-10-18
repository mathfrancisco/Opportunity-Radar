"""Card R55-C3: an unchanged posting is not analysed again.

The key is `content hash + profile version + prompt version` (plus the model options):
the integration side (`cache_hit=true` in `ai_call_record` on a re-run) is covered by
`test_analysis_reuse.py`; here the identity itself is pinned down without a database.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from test_prompt_sections import _POSTINGS, _adapter, _request

from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import default_routes
from opportunity_radar.platform.config import Settings


def _key(adapter: GroqAnalysisAdapter, request: Any) -> str:
    return adapter.prepare(request).cache_key


def test_a_rerun_over_the_same_content_has_the_same_key() -> None:
    adapter = _adapter()

    assert _key(adapter, _request(0)) == _key(adapter, _request(0))


def test_a_changed_posting_text_is_a_new_analysis() -> None:
    adapter = _adapter()
    changed = dict(_POSTINGS[0])
    changed["description"] = changed["description"] + "<p>New requirement: Rust.</p>"

    assert _key(adapter, replace(_request(0), posting=changed)) != _key(adapter, _request(0))


def test_a_new_profile_version_is_a_new_analysis() -> None:
    adapter = _adapter()
    request = _request(0)

    other = replace(request, profile_version_id=UUID(int=100))
    assert _key(adapter, other) != _key(adapter, request)


def test_a_new_prompt_version_is_a_new_analysis() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", ai_analysis_prompt="v3"
    )
    router = AIRouter(provider=None, routes=default_routes(settings))  # type: ignore[arg-type]
    other = GroqAnalysisAdapter(router=router, prompt=load_prompt("v3"))

    assert _key(other, _request(0)) != _key(_adapter(), _request(0))


def test_bookkeeping_that_moves_on_every_recollection_does_not_change_the_key() -> None:
    adapter = _adapter()
    request = _request(0)
    recollected = replace(request, opportunity_content_version=7)

    assert _key(adapter, recollected) == _key(adapter, request)
