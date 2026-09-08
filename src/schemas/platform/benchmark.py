from __future__ import annotations

from datetime import date
import re
from typing import Annotated
from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from .base import PlatformContractModel

_HASH = r"^sha256:[0-9a-f]{64}$"
_BENCHMARK_ID = re.compile(r"^index:[a-z][a-z0-9_-]{0,15}:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class BenchmarkIndexBar(PlatformContractModel):
    """独立指数基准日线契约；不得解析为股票实体。"""

    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [
                {
                    "if": {"properties": {"return_type": {"const": "TOTAL_RETURN"}}},
                    "then": {
                        "required": ["total_return_close"],
                        "properties": {"total_return_close": {"type": "number"}},
                    },
                }
            ]
        }
    )

    benchmark_id: Annotated[str, Field(pattern=r"^index:[a-z][a-z0-9_-]{0,15}:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
    asset_type: str
    trade_date: date
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    return_type: str
    index_name: str | None = Field(default=None, min_length=1, max_length=255)
    total_return_close: float | None = Field(default=None, ge=0)
    available_at: AwareDatetime

    @field_validator("benchmark_id")
    @classmethod
    def validate_benchmark_id(cls, value: str) -> str:
        if not _BENCHMARK_ID.fullmatch(value):
            raise ValueError("benchmark_id must match index:<market>:<code> and contain no path or whitespace characters")
        return value

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, value: str) -> str:
        if value != "index":
            raise ValueError("benchmark asset_type must be index")
        return value

    @field_validator("return_type")
    @classmethod
    def validate_return_type(cls, value: str) -> str:
        if value not in {"PRICE", "TOTAL_RETURN"}:
            raise ValueError("return_type must be PRICE or TOTAL_RETURN")
        return value

    @model_validator(mode="after")
    def validate_prices(self) -> "BenchmarkIndexBar":
        if self.low > self.high or self.open > self.high or self.open < self.low or self.close > self.high or self.close < self.low:
            raise ValueError("benchmark OHLC values are inconsistent")
        if self.return_type == "TOTAL_RETURN" and self.total_return_close is None:
            raise ValueError("TOTAL_RETURN benchmark rows require total_return_close")
        return self


__all__ = ["BenchmarkIndexBar"]
