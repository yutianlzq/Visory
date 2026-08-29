from __future__ import annotations

from pydantic import BaseModel, ConfigDict


_AMBIGUOUS_FIELD_NAMES = frozenset({"status", "version", "date", "timestamp", "hash"})


class PlatformContractModel(BaseModel):
    """Strict immutable base for public platform contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: object) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        ambiguous = sorted(_AMBIGUOUS_FIELD_NAMES.intersection(cls.model_fields))
        if ambiguous:
            fields = ", ".join(ambiguous)
            raise TypeError(f"ambiguous platform contract field: {fields}")
