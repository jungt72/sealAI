import pytest
import uuid
from fastapi import HTTPException
from app.services.chat.validation import normalize_chat_id

def test_normalize_chat_id_empty():
    # Should generate UUID
    cid = normalize_chat_id(None)
    assert uuid.UUID(cid, version=4)
    cid2 = normalize_chat_id("")
    assert uuid.UUID(cid2, version=4)
    assert cid != cid2 # random

def test_normalize_chat_id_valid():
    u = str(uuid.uuid4())
    assert normalize_chat_id(u) == u

def test_normalize_chat_id_invalid():
    invalids = [
        "abc",
        "123",
        str(uuid.uuid4()) + "extra",
        f"prefix-{uuid.uuid4()}",
    ]
    for inv in invalids:
        with pytest.raises(HTTPException) as exc:
            normalize_chat_id(inv)
        assert exc.value.status_code == 400
