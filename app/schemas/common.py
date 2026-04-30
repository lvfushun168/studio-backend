from datetime import datetime

from pydantic import BaseModel, ConfigDict


def _to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake_str.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class ORMModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=_to_camel_case,
    )


class CamelCaseORMModel(BaseModel):
    """Base model that serializes fields to camelCase."""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=_to_camel_case,
    )


class TimestampedRead(CamelCaseORMModel):
    created_at: datetime
    updated_at: datetime
