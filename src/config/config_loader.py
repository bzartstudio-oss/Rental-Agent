import json
from pathlib import Path

from src.models.configuration import (
    Configuration,
    SearchSettings,
    DestinationSettings,
    PreferenceSettings,
    ReportSettings,
)


def load_settings():

    config_path = Path("config/settings.json")

    with open(config_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    search = SearchSettings(**data["search"])

    destination = DestinationSettings(**data["destination"])

    preferences = PreferenceSettings(**data["preferences"])

    reports = ReportSettings(**data["reports"])

    configuration = Configuration(
        project_name=data["project_name"],
        version=data["version"],
        search=search,
        destination=destination,
        preferences=preferences,
        reports=reports,
    )

    return configuration