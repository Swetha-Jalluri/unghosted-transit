"""Pydantic models for the Unghosted contract."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DemoStop(BaseModel):
    """A demo stop for testing."""
    stop_id: str
    name: str
    routes: list[str]


class ChanceBasis(BaseModel):
    """Basis for a probability estimate."""
    method: str = Field(..., pattern="^(model|empirical|placeholder)$")
    n: int


class Evidence(BaseModel):
    """Evidence supporting a prediction."""
    uncertainty: Optional[int] = None
    vehicle_id: Optional[str] = None
    location_age_sec: Optional[int] = None


class Backup(BaseModel):
    """Backup option if primary transit fails."""
    type: str = Field(..., pattern="^(bus|bike)$")
    route_id: Optional[str] = None
    station_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    eta_min: Optional[float] = None
    walk_min: Optional[float] = None
    chance: Optional[float] = None


class BusPrediction(BaseModel):
    """A single bus prediction."""
    route_id: str
    trip_id: str
    headsign: Optional[str] = None
    app_eta_min: float
    status: str = Field(..., pattern="^(confirmed|estimate|unreliable)$")
    why: str
    reason_codes: list[str]
    chance_it_arrives: Optional[float] = None
    chance_basis: ChanceBasis
    realistic_eta_min: tuple[float, float]
    evidence: Evidence
    backup: Optional[Backup] = None
    outcome: Optional[str] = Field(None, pattern="^(served|vanished|canceled|open)$")


class BusTrustResponse(BaseModel):
    """Response for bus trust query."""
    stop_id: str
    stop_name: str
    generated_at: str  # ISO format
    mode: str
    data_age_sec: dict[str, int]
    predictions: list[BusPrediction]
    hidden_count: int
    attribution: list[str]
    disclaimer: str


class DockResult(BaseModel):
    """Result for a single dock."""
    station_id: str
    name: str
    lat: float
    lon: float
    app_bikes: int
    usable_bikes_estimate: tuple[int, int]
    chance_bike_on_arrival: float
    status: str
    why: str
    reason_codes: list[str]
    last_reported_age_sec: Optional[int] = None
    drain_per_min: Optional[float] = None


class DockTrustResponse(BaseModel):
    """Response for dock trust query."""
    generated_at: str  # ISO format
    mode: str
    walk_min: float
    dock: DockResult
    backups: list[DockResult]
    attribution: list[str]
    disclaimer: str


class RateRow(BaseModel):
    """A single rate/metric row."""
    group: str
    rate: float
    n: int


class CalibrationBin(BaseModel):
    """Calibration curve bin."""
    bin: str
    predicted: float
    observed: float
    n: int


class ModelInfo(BaseModel):
    """Model metadata."""
    method: str
    auc: Optional[float] = None
    brier: Optional[float] = None
    n_labels: Optional[int] = None


class EvalInfo(BaseModel):
    """Evaluation metadata."""
    holdout_window: Optional[str] = None
    n_train: int
    n_test: int


class Findings(BaseModel):
    """Overall findings and model calibration."""
    generated_at: str  # ISO format
    sample_label: str
    window: dict[str, int]
    totals: dict[str, int]
    vanish_by_status: list[RateRow]
    vanish_by_uncertainty: list[RateRow]
    vanish_by_route: list[RateRow]
    vanish_by_status_10min: Optional[list[RateRow]] = None  # Optional: status at 10+ min before arrival
    eta_range_hit: dict[str, int]
    least_reliable_docks: list[dict]
    model: ModelInfo
    calibration: list[CalibrationBin]
    eval: EvalInfo
    is_placeholder: bool


class Health(BaseModel):
    """System health snapshot."""
    generated_at: str  # ISO format
    last_poll_ts: Optional[int] = None
    polls_last_hour: int
    poll_success_rate: Optional[float] = None
    rows: dict[str, int]
    data_age_sec: dict[str, int]
    modes: dict[str, bool]
    model_method: str


class ReplayWindow(BaseModel):
    """Time window for replay mode."""
    start: int  # POSIX seconds
    end: int    # POSIX seconds
    step_sec: int
    n_snapshots: int


# Exceptions
class LiveDataUnavailable(Exception):
    """Raised when live data cannot be fetched."""
    pass


class NotFound(Exception):
    """Raised when a requested resource is not found."""
    pass
