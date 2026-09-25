"""Embeddings of the opportunities: the text, the Ollama adapter and the queries over them.

Card F16-09 builds and maintains the vectors; card F16-10 reads them for similar postings,
search by meaning and duplicate candidates. The vector is derived data throughout: it is
rebuilt whenever anything that produced it changes, compared only within one vector space
and one version of the posting, and never decides or merges anything on its own
(SPEC 36, section 15).
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    delete,
    func,
    literal,
    not_,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased, selectinload

from opportunity_radar.matching.currency import active_profile_version_id
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.text import (
    CLEANER_VERSION,
    clean_description,
    truncate_at_sentence,
)
from opportunity_radar.opportunities.embedding_models import (
    EMBEDDING_COLUMN_DIMENSIONS,
    OpportunityEmbeddingFailureModel,
    OpportunityEmbeddingModel,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.logging import get_logger
from opportunity_radar.platform.vector import Vector, cosine_distance

if TYPE_CHECKING:
    from opportunity_radar.dashboard.search_filters import OpportunityFilters

#: Version of the recipe in `embedding_text`. Any change to what goes in, or in what
#: order, bumps it.
EMBEDDING_TEXT_VERSION = "embedding-text-v1"
#: What a stored row names: the recipe and the cleaner it relies on. A new cleaner changes
#: the text of every posting, so it has to re-embed all of them.
TEXT_VERSION = f"{EMBEDDING_TEXT_VERSION}+{CLEANER_VERSION}"
EMBEDDING_TEXT_MAX_CHARS = 6000

#: `qwen3-embedding` expects an instruction before a search query and none before the
#: documents. The instruction is part of the query's vector space, so it is versioned.
QUERY_INSTRUCTION = "Given a job search query, retrieve relevant job postings"
QUERY_INSTRUCTION_VERSION = "job-search-query-v1"

#: A starting cap on one request, to be confirmed on the reference machine: 32 postings
#: of 6 000 characters would be close to 70 000 tokens in a single call.
DEFAULT_MAX_BATCH_CHARS = 96_000
DEFAULT_FAILURE_COOLDOWN = timedelta(minutes=30)
DEFAULT_MAX_ATTEMPTS = 3

_REJECTED = "REJECTED"
_EMBED_PATH = "/api/embed"

logger = get_logger("opportunity_radar.embeddings")


# --- The text ----------------------------------------------------------------------------


def embedding_text(opportunity: OpportunityModel) -> str:
    """The text a posting's vector is computed from.

    Fixed labels in a fixed order, and skills sorted, so the same posting always gives
    the same text and the same hash. The description goes through the analysis cleaner —
    one cleaner for both, never a second one — and takes whatever room the header left.
    """
    skills = sorted(
        {skill.display_name.strip() for skill in opportunity.skills if skill.display_name},
        key=lambda name: (name.casefold(), name),
    )
    fields = (
        ("Title", opportunity.canonical_title),
        ("Company", opportunity.company_name),
        ("Location", opportunity.location_text),
        ("Work mode", _known(opportunity.work_mode)),
        ("Seniority", _known(opportunity.seniority)),
        ("Skills", ", ".join(name for name in skills if name)),
    )
    header = "\n".join(
        f"{label}: {value.strip()}" for label, value in fields if value and value.strip()
    )
    room = max(0, EMBEDDING_TEXT_MAX_CHARS - len(header) - 2)
    description, _ = truncate_at_sentence(clean_description(opportunity.description), room)
    body = f"{header}\n\n{description}" if description else header
    return body[:EMBEDDING_TEXT_MAX_CHARS]


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def query_text(query: str) -> str:
    """The search query as the model expects it."""
    return f"Instruct: {QUERY_INSTRUCTION}\nQuery: {query}"


def _known(value: str | None) -> str | None:
    return None if value in (None, "", "UNKNOWN") else value


# --- The adapter -------------------------------------------------------------------------


class EmbeddingFailureCode(StrEnum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    NON_FINITE = "NON_FINITE"
    # Said by the HTTP layer only: embedding is switched off, so no adapter exists.
    DISABLED = "DISABLED"


#: The model could not be asked at all. No item is to blame, so none is marked as failed.
UNREACHABLE = frozenset(
    {EmbeddingFailureCode.MODEL_UNAVAILABLE, EmbeddingFailureCode.TRANSPORT_ERROR}
)


class EmbeddingError(Exception):
    """A classified embedding failure. `index` names the input it belongs to, if one."""

    def __init__(
        self, code: EmbeddingFailureCode, detail: str, *, index: int | None = None
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.index = index


class EmbeddingPort(Protocol):
    """What the worker needs from an embedding model."""

    @property
    def model(self) -> str: ...

    def embed_each(self, texts: Sequence[str]) -> list[list[float] | EmbeddingError]: ...


class OllamaEmbeddingAdapter:
    """`POST /api/embed`, synchronous, the whole batch in one call.

    Synchronous because its callers are: the worker's jobs run on scheduler threads, and
    the API calls it from a sync endpoint. One `httpx.Client` per adapter keeps the
    connection to Ollama open between calls.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimensions: int,
        timeout_seconds: float = 30.0,
        connect_timeout_seconds: float = 5.0,
        keep_alive: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._url = f"{base_url.rstrip('/')}{_EMBED_PATH}"
        self._model = model
        self._dimensions = dimensions
        self._keep_alive = keep_alive
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                timeout_seconds, connect=min(connect_timeout_seconds, timeout_seconds)
            )
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, or the first classified failure."""
        vectors: list[list[float]] = []
        for result in self.embed_each(texts):
            if isinstance(result, EmbeddingError):
                raise result
            vectors.append(result)
        return vectors

    def embed_query(self, query: str) -> list[float]:
        return self.embed([query_text(query)])[0]

    def embed_each(self, texts: Sequence[str]) -> list[list[float] | EmbeddingError]:
        """One result per text, in order.

        A failure of the call as a whole raises; a bad vector is returned in its own
        position, so it is charged to its own input and the other vectors still count.
        """
        if not texts:
            return []
        payload: dict[str, Any] = {"model": self._model, "input": list(texts)}
        if self._keep_alive is not None:
            payload["keep_alive"] = self._keep_alive
        try:
            response = self._client.post(self._url, json=payload)
        except httpx.TimeoutException as error:
            raise EmbeddingError(
                EmbeddingFailureCode.TIMEOUT, "ollama embedding request timed out"
            ) from error
        except httpx.TransportError as error:
            raise EmbeddingError(
                EmbeddingFailureCode.TRANSPORT_ERROR, "could not connect to ollama"
            ) from error
        _raise_for_status(response)
        embeddings = _embeddings(response, expected=len(texts))
        return [self._checked(item, index) for index, item in enumerate(embeddings)]

    def _checked(self, item: Any, index: int) -> list[float] | EmbeddingError:
        if not isinstance(item, list) or any(
            isinstance(value, bool) or not isinstance(value, int | float) for value in item
        ):
            return EmbeddingError(
                EmbeddingFailureCode.INVALID_RESPONSE,
                "embedding is not a list of numbers",
                index=index,
            )
        if len(item) != self._dimensions:
            return EmbeddingError(
                EmbeddingFailureCode.DIMENSION_MISMATCH,
                f"expected {self._dimensions} dimensions, got {len(item)}",
                index=index,
            )
        vector = [float(value) for value in item]
        if not all(math.isfinite(value) for value in vector):
            return EmbeddingError(
                EmbeddingFailureCode.NON_FINITE,
                "embedding has a non-finite component",
                index=index,
            )
        return vector


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if 200 <= status < 300:
        return
    if status == 404:
        raise EmbeddingError(
            EmbeddingFailureCode.MODEL_UNAVAILABLE,
            "ollama does not have the embedding model installed",
        )
    raise EmbeddingError(EmbeddingFailureCode.SERVER_ERROR, f"ollama returned HTTP {status}")


def _embeddings(response: httpx.Response, *, expected: int) -> list[Any]:
    try:
        envelope = response.json()
    except ValueError as error:
        raise EmbeddingError(
            EmbeddingFailureCode.INVALID_RESPONSE, "ollama returned a non-JSON envelope"
        ) from error
    embeddings = envelope.get("embeddings") if isinstance(envelope, dict) else None
    if not isinstance(embeddings, list) or len(embeddings) != expected:
        raise EmbeddingError(
            EmbeddingFailureCode.INVALID_RESPONSE,
            f"ollama envelope must carry {expected} embedding(s)",
        )
    return embeddings


def build_embedding_adapter(settings: Settings) -> OllamaEmbeddingAdapter | None:
    """One adapter per process, or `None` when embedding is switched off."""
    if not settings.ollama_embedding_enabled:
        return None
    return OllamaEmbeddingAdapter(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model_embedding,
        dimensions=settings.ollama_embedding_dimensions,
        timeout_seconds=settings.ollama_embedding_timeout_seconds,
        keep_alive=settings.ollama_keep_alive,
    )


# --- Keeping the vectors current ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """What one pass did.

    `skipped` items were selected but not attempted — over the batch's character or time
    budget, or left when the model became unreachable — and stay pending. `degraded` says
    why the pass stopped early when the model could not be asked at all.
    """

    selected: int = 0
    embedded: int = 0
    reused: int = 0
    failed: int = 0
    skipped: int = 0
    failures: dict[str, int] = field(default_factory=dict)
    degraded: EmbeddingFailureCode | None = None


@dataclass(frozen=True, slots=True)
class _Item:
    opportunity_id: UUID
    content_version: int
    text: str
    text_hash: str


_Outcome = list[float] | EmbeddingError | None


def current_vector(model: str) -> ColumnElement[bool]:
    """A stored vector that may be compared: same space, same recipe, current posting."""
    return and_(
        OpportunityEmbeddingModel.model == model,
        OpportunityEmbeddingModel.text_version == TEXT_VERSION,
        OpportunityEmbeddingModel.content_version == OpportunityModel.version,
    )


def _pending(
    model: str, *, now: datetime, cooldown: timedelta, max_attempts: int
) -> Select[tuple[UUID]]:
    """Eligible opportunities without a current vector that are not being held back.

    An item is held back while its last failure, for this same identity, is cooling down
    or has used up its attempts. A new version or another model is a new identity, so the
    old failure no longer holds it.
    """
    failure = OpportunityEmbeddingFailureModel
    held = and_(
        failure.model == model,
        failure.text_version == TEXT_VERSION,
        failure.content_version == OpportunityModel.version,
        or_(failure.attempts >= max_attempts, failure.last_attempt_at > now - cooldown),
    )
    return (
        select(OpportunityModel.id)
        .outerjoin(
            OpportunityEmbeddingModel,
            OpportunityEmbeddingModel.opportunity_id == OpportunityModel.id,
        )
        .outerjoin(failure, failure.opportunity_id == OpportunityModel.id)
        .where(
            OpportunityModel.lifecycle_status != _REJECTED,
            or_(OpportunityEmbeddingModel.opportunity_id.is_(None), not_(current_vector(model))),
            or_(failure.opportunity_id.is_(None), not_(held)),
        )
    )


def pending_embedding_ids(
    session: Session,
    *,
    model: str,
    limit: int,
    now: datetime | None = None,
    cooldown: timedelta = DEFAULT_FAILURE_COOLDOWN,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> list[UUID]:
    """The next batch, most recently changed postings first."""
    statement = _pending(
        model, now=now or datetime.now(UTC), cooldown=cooldown, max_attempts=max_attempts
    )
    return list(
        session.scalars(
            statement.order_by(OpportunityModel.updated_at.desc(), OpportunityModel.id).limit(
                limit
            )
        )
    )


def count_pending_embeddings(
    session: Session,
    *,
    model: str,
    now: datetime | None = None,
    cooldown: timedelta = DEFAULT_FAILURE_COOLDOWN,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> int:
    """The backlog the next passes can still take, without the batch cap."""
    statement = _pending(
        model, now=now or datetime.now(UTC), cooldown=cooldown, max_attempts=max_attempts
    )
    return session.scalar(select(func.count()).select_from(statement.subquery())) or 0


def embed_pending(
    session: Session,
    adapter: EmbeddingPort,
    *,
    batch_size: int = 32,
    max_batch_chars: int = DEFAULT_MAX_BATCH_CHARS,
    time_budget_seconds: float = 120.0,
    cooldown: timedelta = DEFAULT_FAILURE_COOLDOWN,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    now: datetime | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> EmbeddingBatch:
    """Embed one bounded batch, committing every item on its own.

    Restart-safe by construction: each vector is an upsert keyed by the opportunity, so a
    pass cut short leaves the finished items finished and the rest pending, and running it
    twice writes nothing new. A posting whose version moved but whose text did not — a
    status change, say — only has its version refreshed, without a model call.
    """
    moment = now or datetime.now(UTC)
    started = clock()
    model = adapter.model
    ids = pending_embedding_ids(
        session,
        model=model,
        limit=batch_size,
        now=moment,
        cooldown=cooldown,
        max_attempts=max_attempts,
    )
    if not ids:
        return EmbeddingBatch()
    items, reusable = _load(session, ids, model=model)
    # Nothing below reads through this transaction; it must not stay open across a call
    # to the model.
    session.commit()

    counts: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    for item in reusable:
        stored = _write(session, item, partial(_refresh, session, item))
        counts["reused" if stored else "failed"] += 1

    sent: list[_Item] = []
    chars = 0
    for item in items:
        if sent and chars + len(item.text) > max_batch_chars:
            break
        sent.append(item)
        chars += len(item.text)
    counts["skipped"] += len(items) - len(sent)

    results, unreachable = _embed_isolating(
        adapter,
        [item.text for item in sent],
        out_of_time=lambda: clock() - started >= time_budget_seconds,
    )
    for item, result in zip(sent, results, strict=True):
        if result is None:
            counts["skipped"] += 1
        elif isinstance(result, EmbeddingError):
            failures[result.code.value] += 1
            counts["failed"] += 1
            _write(session, item, partial(_record_failure, session, item, model, result, moment))
        elif _write(session, item, partial(_upsert, session, item, model, result)):
            counts["embedded"] += 1
        else:
            counts["failed"] += 1
    return EmbeddingBatch(
        selected=len(ids),
        embedded=counts["embedded"],
        reused=counts["reused"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        failures=dict(failures),
        degraded=unreachable.code if unreachable else None,
    )


def _load(
    session: Session, ids: Sequence[UUID], *, model: str
) -> tuple[list[_Item], list[_Item]]:
    """The items to embed, and the ones whose stored vector already fits their text."""
    rows = session.execute(
        select(
            OpportunityModel,
            OpportunityEmbeddingModel.model,
            OpportunityEmbeddingModel.text_version,
            OpportunityEmbeddingModel.text_hash,
        )
        .outerjoin(
            OpportunityEmbeddingModel,
            OpportunityEmbeddingModel.opportunity_id == OpportunityModel.id,
        )
        .where(OpportunityModel.id.in_(ids))
        .options(selectinload(OpportunityModel.skills))
    ).all()
    by_id = {row[0].id: row for row in rows}
    items: list[_Item] = []
    reusable: list[_Item] = []
    for opportunity_id in ids:
        row = by_id.get(opportunity_id)
        if row is None:  # deleted between the two reads
            continue
        opportunity, stored_model, stored_version, stored_hash = row
        body = embedding_text(opportunity)
        item = _Item(opportunity.id, opportunity.version, body, text_hash(body))
        same_text = (
            stored_model == model
            and stored_version == TEXT_VERSION
            and stored_hash == item.text_hash
        )
        (reusable if same_text else items).append(item)
    return items, reusable


def _embed_isolating(
    adapter: EmbeddingPort, texts: Sequence[str], *, out_of_time: Callable[[], bool]
) -> tuple[list[_Outcome], EmbeddingError | None]:
    """One call for the whole batch; one call per item only if the batch call failed.

    `None` marks an item that was not attempted. The error returned beside the results is
    set when the model could not be reached at all, which ends the pass without charging
    any item for it.
    """
    if not texts:
        return [], None
    try:
        whole: list[_Outcome] = list(adapter.embed_each(texts))
        return whole, None
    except EmbeddingError as error:
        if error.code in UNREACHABLE:
            untouched: list[_Outcome] = [None] * len(texts)
            return untouched, error
        if len(texts) == 1:
            return [error], None
    # A batch the server refused or did not finish may be one bad input among good ones.
    # Alone, each item answers for itself, for as long as the pass has time.
    results: list[_Outcome] = []
    for position, body in enumerate(texts):
        if out_of_time():
            results.extend([None] * (len(texts) - position))
            break
        try:
            results.extend(adapter.embed_each([body]))
        except EmbeddingError as error:
            if error.code in UNREACHABLE:
                results.extend([None] * (len(texts) - position))
                return results, error
            results.append(error)
    return results, None


def _write(session: Session, item: _Item, operation: Callable[[], None]) -> bool:
    """Run one item's write in its own transaction; a database error costs only that item."""
    try:
        operation()
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception(
            "embedding could not be stored",
            extra={"job": "embed", "opportunity_id": str(item.opportunity_id)},
        )
        return False
    return True


def _upsert(session: Session, item: _Item, model: str, vector: list[float]) -> None:
    statement = insert(OpportunityEmbeddingModel).values(
        opportunity_id=item.opportunity_id,
        content_version=item.content_version,
        model=model,
        text_version=TEXT_VERSION,
        text_hash=item.text_hash,
        dimensions=len(vector),
        embedding=vector,
    )
    excluded = statement.excluded
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["opportunity_id"],
            set_={
                "content_version": excluded.content_version,
                "model": excluded.model,
                "text_version": excluded.text_version,
                "text_hash": excluded.text_hash,
                "dimensions": excluded.dimensions,
                "embedding": excluded.embedding,
                "updated_at": func.now(),
            },
        )
    )
    _clear_failure(session, item)


def _refresh(session: Session, item: _Item) -> None:
    session.execute(
        update(OpportunityEmbeddingModel)
        .where(
            OpportunityEmbeddingModel.opportunity_id == item.opportunity_id,
            OpportunityEmbeddingModel.text_hash == item.text_hash,
        )
        .values(content_version=item.content_version, updated_at=func.now())
    )
    _clear_failure(session, item)


def _clear_failure(session: Session, item: _Item) -> None:
    session.execute(
        delete(OpportunityEmbeddingFailureModel).where(
            OpportunityEmbeddingFailureModel.opportunity_id == item.opportunity_id
        )
    )


def _record_failure(
    session: Session, item: _Item, model: str, error: EmbeddingError, moment: datetime
) -> None:
    """Count the attempt against this identity; another identity starts from one."""
    table = OpportunityEmbeddingFailureModel.__table__
    statement = insert(OpportunityEmbeddingFailureModel).values(
        opportunity_id=item.opportunity_id,
        content_version=item.content_version,
        model=model,
        text_version=TEXT_VERSION,
        failure_code=error.code.value,
        detail=error.detail[:1000],
        attempts=1,
        first_failed_at=moment,
        last_attempt_at=moment,
    )
    excluded = statement.excluded
    same_identity = and_(
        table.c.model == excluded.model,
        table.c.text_version == excluded.text_version,
        table.c.content_version == excluded.content_version,
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["opportunity_id"],
            set_={
                "attempts": case((same_identity, table.c.attempts + 1), else_=1),
                "first_failed_at": case(
                    (same_identity, table.c.first_failed_at), else_=excluded.first_failed_at
                ),
                "content_version": excluded.content_version,
                "model": excluded.model,
                "text_version": excluded.text_version,
                "failure_code": excluded.failure_code,
                "detail": excluded.detail,
                "last_attempt_at": excluded.last_attempt_at,
            },
        )
    )


# --- Coverage ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmbeddingCoverage:
    """How much of the collection the configured model's index covers right now.

    `given_up` counts pending postings whose attempts are used up for their current
    version; they come back only when the posting or the model changes.
    """

    model: str
    current: int
    eligible: int
    given_up: int
    oldest_pending_at: datetime | None

    @property
    def complete(self) -> bool:
        return self.current >= self.eligible

    @property
    def pending(self) -> int:
        return max(0, self.eligible - self.current)


def embedding_coverage(
    session: Session, *, model: str, max_attempts: int = DEFAULT_MAX_ATTEMPTS
) -> EmbeddingCoverage:
    """Current vectors against eligible (non-rejected) opportunities.

    A partial index is the normal state while a model change is being rebuilt; the
    consumer decides what to do with it, and the Inbox keeps full-text meanwhile.
    """
    failure = OpportunityEmbeddingFailureModel
    current = current_vector(model)
    pending = or_(OpportunityEmbeddingModel.opportunity_id.is_(None), not_(current))
    exhausted = and_(
        pending,
        failure.model == model,
        failure.text_version == TEXT_VERSION,
        failure.content_version == OpportunityModel.version,
        failure.attempts >= max_attempts,
    )
    row = session.execute(
        select(
            func.count(OpportunityModel.id),
            func.count(OpportunityEmbeddingModel.opportunity_id).filter(current),
            func.count(failure.opportunity_id).filter(exhausted),
            func.min(OpportunityModel.updated_at).filter(pending),
        )
        .outerjoin(
            OpportunityEmbeddingModel,
            OpportunityEmbeddingModel.opportunity_id == OpportunityModel.id,
        )
        .outerjoin(failure, failure.opportunity_id == OpportunityModel.id)
        .where(OpportunityModel.lifecycle_status != _REJECTED)
    ).one()
    eligible, covered, given_up, oldest = row
    return EmbeddingCoverage(
        model=model,
        current=covered or 0,
        eligible=eligible or 0,
        given_up=given_up or 0,
        oldest_pending_at=oldest,
    )


# --- Reading the vectors -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RelatedOpportunity:
    """A neighbour: what the operator needs to recognise it, and how close it is.

    `verdict` is the latest assessment against the active profile, when there is one: the
    point of a similar posting is to see how its likes were decided.
    """

    id: UUID
    title: str
    company_name: str | None
    verdict: str | None
    similarity: float


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    first_id: UUID
    second_id: UUID
    company_id: UUID
    similarity: float


def similar_opportunities(
    session: Session, opportunity_id: UUID, *, model: str, limit: int = 5
) -> list[RelatedOpportunity] | None:
    """The nearest postings by cosine, or `None` when this one has no current vector.

    The posting itself is excluded by id, not by distance: its distance to itself is 0,
    and so is a true duplicate's.
    """
    source = session.scalar(
        select(OpportunityEmbeddingModel.embedding)
        .join(OpportunityModel, OpportunityModel.id == OpportunityEmbeddingModel.opportunity_id)
        .where(OpportunityEmbeddingModel.opportunity_id == opportunity_id, current_vector(model))
    )
    if source is None:
        return None
    distance = _distance_to(source)
    _complete_filtered_pages(session)
    rows = session.execute(
        select(OpportunityEmbeddingModel.opportunity_id, distance)
        .join(OpportunityModel, OpportunityModel.id == OpportunityEmbeddingModel.opportunity_id)
        .where(OpportunityEmbeddingModel.opportunity_id != opportunity_id, current_vector(model))
        .order_by(distance, OpportunityEmbeddingModel.opportunity_id)
        .limit(limit)
    ).all()
    return describe_opportunities(session, [(row[0], 1.0 - float(row[1])) for row in rows])


def semantic_search_ids(
    session: Session,
    query_vector: Sequence[float],
    *,
    model: str,
    filters: OpportunityFilters,
    limit: int,
    offset: int = 0,
) -> list[tuple[UUID, float]]:
    """Opportunity ids by similarity to the query, under the full-text search's filters.

    Ordered by distance and then by id, so pages do not overlap or skip when two postings
    are equally close.
    """
    # Imported here: the dashboard package loads its read models on import, and those may
    # one day read these vectors.
    from opportunity_radar.dashboard.search_filters import opportunity_conditions

    distance = _distance_to(query_vector)
    _complete_filtered_pages(session)
    rows = session.execute(
        select(OpportunityEmbeddingModel.opportunity_id, distance)
        .join(OpportunityModel, OpportunityModel.id == OpportunityEmbeddingModel.opportunity_id)
        .where(current_vector(model), *opportunity_conditions(filters))
        .order_by(distance, OpportunityEmbeddingModel.opportunity_id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [(row[0], 1.0 - float(row[1])) for row in rows]


def describe_opportunities(
    session: Session, ranked: Sequence[tuple[UUID, float]]
) -> list[RelatedOpportunity]:
    """Title, company and current verdict for ranked ids, keeping their order."""
    if not ranked:
        return []
    rows = session.execute(
        select(
            OpportunityModel.id,
            OpportunityModel.canonical_title,
            OpportunityModel.company_name,
            _current_verdict(),
        ).where(OpportunityModel.id.in_([opportunity_id for opportunity_id, _ in ranked]))
    ).all()
    found = {row[0]: row for row in rows}
    related: list[RelatedOpportunity] = []
    for opportunity_id, similarity in ranked:
        row = found.get(opportunity_id)
        if row is None:
            continue
        related.append(
            RelatedOpportunity(
                id=opportunity_id,
                title=row[1],
                company_name=row[2],
                verdict=row[3],
                similarity=similarity,
            )
        )
    return related


def duplicate_candidates(
    session: Session, *, model: str, threshold: float = 0.95, limit: int = 100
) -> list[DuplicateCandidate]:
    """Pairs of the same canonical company whose current vectors nearly coincide.

    A signal for the duplicate review of card F17-08, never a merge: one company posting
    the same role twice, for two openings, is legitimately alike.
    """
    first = aliased(OpportunityEmbeddingModel)
    second = aliased(OpportunityEmbeddingModel)
    first_posting = aliased(OpportunityModel)
    second_posting = aliased(OpportunityModel)
    distance = cosine_distance(first.embedding, second.embedding)
    rows = session.execute(
        select(
            first.opportunity_id,
            second.opportunity_id,
            first_posting.canonical_company_id,
            distance,
        )
        .select_from(first)
        .join(first_posting, first_posting.id == first.opportunity_id)
        .join(
            second_posting,
            and_(
                second_posting.canonical_company_id == first_posting.canonical_company_id,
                second_posting.id > first_posting.id,
            ),
        )
        .join(second, second.opportunity_id == second_posting.id)
        .where(
            first_posting.canonical_company_id.is_not(None),
            first.model == model,
            first.text_version == TEXT_VERSION,
            first.content_version == first_posting.version,
            second.model == model,
            second.text_version == TEXT_VERSION,
            second.content_version == second_posting.version,
            distance <= 1.0 - threshold,
        )
        .order_by(distance, first.opportunity_id, second.opportunity_id)
        .limit(limit)
    ).all()
    return [
        DuplicateCandidate(
            first_id=row[0], second_id=row[1], company_id=row[2], similarity=1.0 - float(row[3])
        )
        for row in rows
    ]


def _distance_to(vector: Sequence[float]) -> ColumnElement[float]:
    """Distance from the stored vectors to one vector bound as a `vector(1024)` parameter."""
    return cosine_distance(
        OpportunityEmbeddingModel.embedding,
        literal(list(vector), Vector(EMBEDDING_COLUMN_DIMENSIONS)),
    )


def _complete_filtered_pages(session: Session) -> None:
    """Keep an HNSW scan going until the filtered page is full, in exact order.

    Without it, the index returns its `ef_search` nearest rows and the filters run after,
    which can leave a page short (pgvector 0.8, iterative index scans). Local to the
    current transaction.
    """
    session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))


def _current_verdict() -> Any:
    return (
        select(MatchAssessmentModel.verdict)
        .where(
            MatchAssessmentModel.opportunity_id == OpportunityModel.id,
            MatchAssessmentModel.profile_version_id == active_profile_version_id(),
        )
        .order_by(MatchAssessmentModel.assessed_at.desc(), MatchAssessmentModel.id.desc())
        .limit(1)
        .correlate(OpportunityModel)
        .scalar_subquery()
    )


__all__ = [
    "DEFAULT_FAILURE_COOLDOWN",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_BATCH_CHARS",
    "EMBEDDING_TEXT_MAX_CHARS",
    "EMBEDDING_TEXT_VERSION",
    "QUERY_INSTRUCTION",
    "QUERY_INSTRUCTION_VERSION",
    "TEXT_VERSION",
    "UNREACHABLE",
    "DuplicateCandidate",
    "EmbeddingBatch",
    "EmbeddingCoverage",
    "EmbeddingError",
    "EmbeddingFailureCode",
    "EmbeddingPort",
    "OllamaEmbeddingAdapter",
    "RelatedOpportunity",
    "build_embedding_adapter",
    "count_pending_embeddings",
    "current_vector",
    "describe_opportunities",
    "duplicate_candidates",
    "embed_pending",
    "embedding_coverage",
    "embedding_text",
    "pending_embedding_ids",
    "query_text",
    "semantic_search_ids",
    "similar_opportunities",
    "text_hash",
]
