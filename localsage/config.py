"""Handles all user-facing configuration actions."""

import json
import os

from localsage.globals import CONFIG_FILE


class Config:
    """User-facing configuration variables"""

    def __init__(self):
        self.models: list[dict] = [
            {
                "alias": "default",
                "name": "Sage",
                "endpoint": "http://localhost:8080/v1",
                "api_key": "stored",
            }
        ]
        # Default values
        self.active_model: str = "default"
        self.context_length: int = 131072
        self.refresh_rate: int = 30
        self.rich_code_theme: str = "monokai"
        self.reasoning_panel_consume: bool = True
        self.system_prompt: str = "You are Sage, a conversational AI assistant."

    def active(self) -> dict:
        """Return the currently active model profile."""
        for m in self.models:
            if m["alias"] == self.active_model:
                return m
        return self.models[0]

    def save(self):
        """Saves any config changes to the config file."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2)

    def load(self):
        """Loads the config file."""
        if not os.path.exists(CONFIG_FILE):
            self.save()
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, val in data.items():
            setattr(self, key, val)

    @property
    def endpoint(self) -> str:
        """Returns the API endpoint for use in Chat"""
        return self.active()["endpoint"]

    @property
    def model_name(self) -> str:
        """Returns the model name for use in Chat"""
        return self.active()["name"]

    @property
    def alias_name(self) -> str:
        """Returns the profile name for use in Chat"""
        return self.active()["alias"]
