"""D3 planning data. Defaults contain no message, canary or system prompt."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Fields(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ShortText = Annotated[str, Field(max_length=255)]
Source = Annotated[str, Field(max_length=16000)]
ModelTag = Annotated[str, Field(max_length=128, pattern=r"^[a-zA-Z0-9._:/-]*$")]


class MailDraft(Fields):
    subject: ShortText = ""
    body: Source = ""


class Variation(MailDraft):
    name: ShortText = ""
    later_subject: ShortText = ""
    later_body: Source = ""


class Vector(Fields):
    count: int = Field(default=4, ge=4, le=5)
    variations: list[Variation] = Field(
        default_factory=lambda: [Variation() for _ in range(5)], min_length=5, max_length=5
    )


class ThreadVariation(Variation):
    # The original subject/body and later_* pair remain the first two reply turns.
    prior_emails: list[MailDraft] = Field(default_factory=list)
    additional_followups: list[MailDraft] = Field(default_factory=list)


class ThreadVector(Vector):
    variations: list[ThreadVariation] = Field(
        default_factory=lambda: [ThreadVariation() for _ in range(5)], min_length=5, max_length=5
    )


class Vectors(Fields):
    v1: Vector = Field(default_factory=Vector)
    v2: Vector = Field(default_factory=Vector)
    v3: ThreadVector = Field(default_factory=ThreadVector)


class PlanSettings(Fields):
    models: list[ModelTag] = Field(
        default_factory=lambda: ["llama3.1:8b-instruct-q4_K_M", ""], min_length=2, max_length=2
    )
    repetitions: int = Field(default=20, ge=5, le=200)
    system_prompt: Source = ""
    fixed_value: Source = ""
    canaries: Source = ""

    @model_validator(mode="after")
    def distinct_models(self):
        if self.models[0] and self.models[0] == self.models[1]:
            raise ValueError("Choose two distinct model tags.")
        return self


class Plan(PlanSettings):
    vectors: Vectors = Field(default_factory=Vectors)


class SavePlan(Fields):
    revision: int = Field(ge=0)
    plan: Plan


class VariationFile(Fields):
    revision: int = Field(ge=0)
    setup: PlanSettings
    active_variations: int = Field(ge=4, le=5)
    variation_number: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def active_slot(self):
        if self.variation_number > self.active_variations:
            raise ValueError("The variation number exceeds the active variation count.")
        return self


class SingleMailFile(VariationFile):
    vector: Literal["v1", "v2"]
    variation: Variation


class ThreadFile(VariationFile):
    vector: Literal["v3"]
    variation: ThreadVariation
