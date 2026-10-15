"""Shared configuration validation for host maintenance and container startup."""

SAVE_PATH = "/home/steam/enshrouded/saves"


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Server configuration must be a JSON object")
    if type(config.get("slotCount")) is not int or not 1 <= config["slotCount"] <= 16:
        raise ValueError("slotCount must be an integer from 1 to 16")
    if config.get("ip") != "0.0.0.0" or config.get("queryPort") != 15637:
        raise ValueError("This Compose setup requires ip=0.0.0.0 and queryPort=15637")
    if config.get("saveDirectory") != SAVE_PATH:
        raise ValueError(f"saveDirectory must remain {SAVE_PATH}")
    groups = config.get("userGroups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("At least one password-protected user group is required")
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("Each user group must be a JSON object")
        password = group.get("password")
        if not isinstance(password, str) or not password.strip():
            raise ValueError("Every user group needs a nonempty password")
