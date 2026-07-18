from __future__ import annotations

from alembic import command
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from sealai_v2.db.migrate import _config, migration_status
from sealai_v2.tests.test_mat_evid_ai_review_domain import _adjudicator
from sealai_v2.tests.test_mat_evid_ai_review_persistence import (
    AI_TABLES,
    CREATED_AT,
    _challenge,
    _setup,
)
from sealai_v2.material_evidence_ai_review.audit import create_adjudication


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def test_real_postgres_ai_review_fingerprint_lifecycle_and_immutability(
    tmp_path,
) -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_mat_evid_ai_review_test")

    from sealai_v2.db.engine import make_engine

    clean = make_engine(POSTGRES_URL)
    assert inspect(clean).get_table_names() == []
    clean.dispose()

    engine, _, repo, context, snapshot = _setup(
        tmp_path,
        database_url=POSTGRES_URL,
    )
    assert migration_status(engine) == ("20260718_0019", "20260718_0019")
    assert AI_TABLES <= set(inspect(engine).get_table_names())

    receipt = _challenge(snapshot, tmp_path)
    challenge = receipt.challenge
    repo.record_challenge(
        receipt=receipt,
        context=context,
        created_at=CREATED_AT,
    )
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-postgres-adjudicator"),
        finding_adjudications=(),
    )
    repo.record_adjudication(
        adjudication=adjudication,
        context=context,
        created_at=CREATED_AT,
    )
    assert repo.load_snapshot(snapshot.review_snapshot_id, context=context) == snapshot

    for table in sorted(AI_TABLES):
        with pytest.raises(DBAPIError, match="MAT-EVID AI immutable table"):
            with engine.begin() as connection:
                connection.execute(text(f'UPDATE "{table}" SET created_at=created_at'))

    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0018")
    assert migration_status(engine)[0] == "20260718_0019"
