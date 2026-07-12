import json
from pathlib import Path


def load_settings():

    config_path = Path("config/settings.json")

    with open(config_path, "r", encoding="utf-8") as file:
        settings = json.load(file)

    return settings