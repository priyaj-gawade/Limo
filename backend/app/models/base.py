"""Base Pydantic model for all Limo domain models."""

from pydantic import BaseModel, ConfigDict


class LimoBaseModel(BaseModel):
    """Common base model enforcing Pydantic v2 configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=False,
    )
