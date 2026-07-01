"""Shared schema utilities."""

from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base Pydantic model configured with a camelCase alias generator.

    Applies to both directions:
    - Output (serialization): fields always render as camelCase, e.g.
      ``first_name`` -> ``"firstName"`` in JSON responses.
    - Input (validation): ``populate_by_name=True`` means both camelCase
      (``firstName``) and the underlying snake_case attribute name
      (``first_name``) are accepted. This is intentional — it lets internal
      callers (tests, other services) construct schemas using Python-native
      snake_case kwargs, while external API clients send camelCase JSON.
    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
        populate_by_name=True,
        from_attributes=True,
    )
