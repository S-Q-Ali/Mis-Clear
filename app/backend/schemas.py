"""API contracts (input/output schemas). Contract-first: types are the docs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

TargetType = Literal["email", "username", "image", "custom"]
ScanMode = Literal["local", "hybrid"]
Confidence = Literal["confirmed", "probable", "possible", "weak", "false_positive"]
Severity = Literal["critical", "high", "medium", "low", "informational"]
JobStatus = Literal["queued", "running", "completed", "interrupted", "failed"]
ScanStatus = Literal["pending", "running", "completed", "failed", "interrupted"]


class Camelised(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, ser_json_by_alias=True)


# ---------- Inputs ----------

class ScanCreate(BaseModel):
    targetType: TargetType
    targetValue: str = Field(max_length=255)
    scanMode: ScanMode = "local"

    @field_validator("targetValue")
    @classmethod
    def _validate_target(cls, v: str, info) -> str:
        v = v.strip()
        if info.data.get("targetType") == "image":
            return v or "(image)"
        if not v:
            raise ValueError("targetValue must not be blank")
        if info.data.get("targetType") == "email" and "@" not in v:
            raise ValueError("targetValue must be a valid-looking email for targetType=email")
        return v


class JobCreate(BaseModel):
    jobId: str = Field(min_length=1, max_length=36)
    jobType: str = Field(min_length=1, max_length=40)
    privacyMode: str = "hybrid_approved"
    scanId: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    requestedCapabilities: list[str] = Field(default_factory=list)
    expiresAt: datetime | None = None


# ---------- Outputs ----------

def forward(names: tuple[str, ...]):
    """Field whose JSON name is camelCase but ORM attribute is snake_case."""
    return Field(validation_alias=AliasChoices(*names))


class ScanOut(Camelised):
    id: int
    targetType: str = forward(("targetType", "target_type"))
    targetValue: str = forward(("targetValue", "target_value"))
    scanMode: str = forward(("scanMode", "scan_mode"))
    status: str
    createdAt: datetime = forward(("createdAt", "created_at"))
    startedAt: datetime | None = forward(("startedAt", "started_at"))
    completedAt: datetime | None = forward(("completedAt", "completed_at"))
    coverage: dict[str, Any] | None = None
    error: str | None = None


class FindingOut(Camelised):
    id: int
    scanId: int = forward(("scanId", "scan_id"))
    type: str
    title: str
    source: str
    url: str | None = None
    evidence: str | None = None
    confidence: str
    severity: str
    timestamp: datetime
    scope: str | None = None
    tool: str | None = None
    status: str
    actionId: int | None = None


class ToolRunOut(Camelised):
    id: int
    scanId: int | None = forward(("scanId", "scan_id"))
    tool: str
    status: str
    durationMs: int = forward(("durationMs", "duration_ms"))
    coverage: str | None = None
    findingsCount: int = forward(("findingsCount", "findings_count"))
    errors: list[str] | None = None
    rawReference: str | None = forward(("rawReference", "raw_reference"))
    startedAt: datetime = forward(("startedAt", "started_at"))
    completedAt: datetime | None = forward(("completedAt", "completed_at"))


class ImageOut(Camelised):
    id: int
    scanId: int | None = forward(("scanId", "scan_id"))
    filename: str
    localPath: str = forward(("localPath", "local_path"))
    md5: str | None = None
    sha256: str | None = None
    phash: str | None = None
    exif: dict[str, Any] | None = None
    createdAt: datetime = forward(("createdAt", "created_at"))


class JobOut(Camelised):
    id: int
    jobId: str = forward(("jobId", "job_id"))
    scanId: int | None = forward(("scanId", "scan_id"))
    jobType: str = forward(("jobType", "job_type"))
    protocolVersion: str = forward(("protocolVersion", "protocol_version"))
    status: str
    privacyMode: str = forward(("privacyMode", "privacy_mode"))
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    errors: list[str] | None = None
    dataDeleted: bool = forward(("dataDeleted", "data_deleted"))
    requestedCapabilities: list[str] | None = None
    worker: str | None = None
    createdAt: datetime = forward(("createdAt", "created_at"))
    startedAt: datetime | None = forward(("startedAt", "started_at"))
    completedAt: datetime | None = forward(("completedAt", "completed_at"))
    expiresAt: datetime | None = forward(("expiresAt", "expires_at"))


class WorkerStatusOut(BaseModel):
    mode: Literal["local_only", "hybrid", "offline"]
    localAiConfigured: bool
    localAiAvailable: bool = False
    colabAiConfigured: bool
    colabAiAvailable: bool = False
    colabDispatcherConfigured: bool
    colabApprovalRequired: bool


class GraphNode(BaseModel):
    id: list[str]
    kind: str
    value: str
    canonical: str
    scanCount: int
    evidenceCount: int


class GraphEdge(BaseModel):
    source: list[str]
    target: list[str]
    type: str
    evidenceFindingId: int | None = None


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ReportSummary(BaseModel):
    scan: ScanOut
    totalFindings: int
    bySeverity: dict[str, int]
    byConfidence: dict[str, int]
    toolsRun: int
    sourcesChecked: list[str]
    aiAvailable: bool


class RiskBreakdownOut(BaseModel):
    severity: float
    confidence: float
    sourceReliability: float
    sensitivity: float
    exposureAge: float
    correlation: float
    score: float
    riskScore: int
    level: str
    gated: bool = False
    extra: dict[str, Any] = {}


class FindingRiskOut(BaseModel):
    findingId: int
    type: str
    title: str
    score: float
    riskScore: int
    level: str
    breakdown: RiskBreakdownOut


class ScanRiskOut(BaseModel):
    scanId: int
    riskScore: int
    level: str
    averageRiskScore: int
    findingCount: int
    findings: list[FindingRiskOut]


class PrivacyActionOut(Camelised):
    id: int
    findingId: int | None = forward(("findingId", "finding_id"))
    recommendedAction: str = forward(("recommendedAction", "recommended_action"))
    deletionUrl: str | None = forward(("deletionUrl", "deletion_url"))
    instructions: str | None = forward(("instructions", "instructions"))
    evidenceReference: str | None = forward(("evidenceReference", "evidence_reference"))
    approvalRequired: bool = forward(("approvalRequired", "approval_required"))
    status: str
    createdAt: datetime = forward(("createdAt", "created_at"))
    approvedAt: datetime | None = forward(("approvedAt", "approved_at"))
    siteAdvisory: dict[str, Any] | None = None
    execution: dict[str, Any] | None = None


class DeletionResearchOut(BaseModel):
    scanId: int
    researchable: int
    created: int
    skipped: int


class ActionTransitionOut(BaseModel):
    id: int
    status: str


class RemovalOut(BaseModel):
    findingId: int
    actionId: int
    status: str
    execution: dict[str, Any] | None = None


class LogOut(Camelised):
    id: int
    timestamp: datetime
    actor: str
    action: str
    entityType: str = forward(("entityType", "entity_type"))
    entityId: int | None = forward(("entityId", "entity_id"))
    detail: str | None = None


class SettingsOut(BaseModel):
    """Read-only config surface — no write endpoint exists by design."""

    readOnly: bool = True
    osintEnabled: bool
    defaultScanMode: str
    hybridRequiresExplicitApproval: bool
    localAiConfigured: bool
    localAiAvailable: bool
    colabAiConfigured: bool
    colabAiAvailable: bool
    colabDispatcherConfigured: bool
    colabApprovalRequired: bool
    uploadMaxBytes: int


class Pagination(BaseModel):
    page: int
    pageSize: int
    totalItems: int
    totalPages: int


T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    data: list[T]
    pagination: Pagination


PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100


def pagination_meta(total_items: int, page: int, page_size: int) -> Pagination:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    if total_items == 0:
        total_pages = 1
    return Pagination(page=page, pageSize=page_size, totalItems=total_items, totalPages=total_pages)