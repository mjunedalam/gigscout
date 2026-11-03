"""Loads and validates a YAML agency profile."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from gigscout.models import AgencyProfile


class ProfileError(ValueError):
    pass


def load_profile(path: Path) -> AgencyProfile:
    if not path.is_file():
        raise ProfileError(f"Profile file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return AgencyProfile.model_validate(data)
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path} is not valid YAML: {exc}") from exc
    except ValidationError as exc:
        raise ProfileError(f"{path} is not a valid agency profile:\n{exc}") from exc
