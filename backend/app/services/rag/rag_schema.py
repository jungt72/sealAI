from __future__ import annotations

import hashlib
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class Domain(str, Enum):
    MATERIAL = "material"
    STANDARD = "standard"
    PRODUCT = "product"
    TROUBLESHOOTING = "troubleshooting"


class MaterialFamily(str, Enum):
    NBR = "NBR"
    FKM = "FKM"
    EPDM = "EPDM"
    PTFE = "PTFE"


class SourceType(str, Enum):
    MANUAL = "manual"
    UPLOAD = "upload"
    CRAWL = "crawl"


class EngineeringProps(BaseModel):
    material_family: Optional[str] = None


class TempRange(BaseModel):
    model_config = ConfigDict(strict=True)

    min_c: float
    max_c: float


class ChunkMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    tenant_id: str
    doc_id: str
    document_id: str
    chunk_id: str
    chunk_hash: str
    source_uri: str
    source_type: SourceType = SourceType.MANUAL
    domain: Domain = Domain.MATERIAL
    chunk_index: int
    entity: Optional[str] = None
    aspect: list[str] = Field(default_factory=list)
    language: Optional[str] = None
    source_version: Optional[str] = None
    effective_date: Optional[str] = None
    category: Optional[str] = None
    route_key: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    source_system: Optional[str] = None
    source_document_id: Optional[str] = None
    source_modified_at: Optional[str] = None
    material_code: str
    source_url: Optional[str] = None
    shore_hardness: int
    temp_range: TempRange
    additional_metadata: Dict[str, Any] = Field(default_factory=dict)
    title: Optional[str] = None
    page_number: Optional[int] = None
    text: str = ""
    created_at: float = 0.0
    visibility: str = "public"
    eng: EngineeringProps = Field(default_factory=EngineeringProps)

    @staticmethod
    def compute_hash(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def generate_chunk_id(tenant_id: str, document_id: str, chunk_index: int) -> str:
        raw = f"{tenant_id}:{document_id}:{chunk_index}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))
