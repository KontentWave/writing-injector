from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from .config import ConfigurationError
from .models import MAX_MATRIX_MODELS, MAX_MATRIX_REQUESTS, ModelParams, ModelProfile

MODEL_PROFILES: Mapping[str, ModelProfile] = MappingProxyType(
    {
        model_id: ModelProfile(ModelParams(model=model_id), supported)
        for model_id, supported in (
            (
                "anthracite-org/magnum-v4-72b",
                ("temperature", "min_p", "top_p", "repetition_penalty"),
            ),
            ("deepseek/deepseek-chat-v3-0324", ("temperature", "top_p")),
            (
                "sao10k/l3.1-euryale-70b",
                ("temperature", "min_p", "top_p", "repetition_penalty"),
            ),
        )
    }
)


def validate_matrix_request(profiles: tuple[ModelProfile, ...], n: int) -> None:
    if not 2 <= len(profiles) <= MAX_MATRIX_MODELS:
        raise ConfigurationError("--models requires two or three registered model IDs.")
    if len({profile.model_id for profile in profiles}) != len(profiles):
        raise ConfigurationError("--models must not contain duplicate model IDs.")
    for profile in profiles:
        registered = MODEL_PROFILES.get(profile.model_id)
        if registered is None or profile.supported_parameters != registered.supported_parameters:
            raise ConfigurationError("Matrix models must use registered parameter support.")
    if n < 1 or len(profiles) * n > MAX_MATRIX_REQUESTS:
        raise ConfigurationError("Matrix mode permits at most nine initial candidate requests.")


def select_model_profiles(
    model_list: str, *, temperature: float | None = None, min_p: float | None = None
) -> tuple[ModelProfile, ...]:
    model_ids = tuple(part.strip() for part in model_list.split(","))
    if any(not model_id for model_id in model_ids):
        raise ConfigurationError("--models must not contain empty model IDs.")
    if len(set(model_ids)) != len(model_ids):
        raise ConfigurationError("--models must not contain duplicate model IDs.")
    if any(model_id not in MODEL_PROFILES for model_id in model_ids):
        raise ConfigurationError(
            "--models contains an unknown model ID; registered full IDs: "
            + ", ".join(MODEL_PROFILES)
        )
    profiles = tuple(MODEL_PROFILES[model_id] for model_id in model_ids)
    validate_matrix_request(profiles, 1)
    if min_p is not None and any(
        "min_p" not in profile.supported_parameters for profile in profiles
    ):
        raise ConfigurationError("--min-p requires support in every selected matrix model.")
    return tuple(
        replace(
            profile,
            params=replace(
                profile.params,
                temperature=profile.params.temperature if temperature is None else temperature,
                min_p=profile.params.min_p if min_p is None else min_p,
            ),
        )
        for profile in profiles
    )
