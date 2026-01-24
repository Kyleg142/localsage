"""Attachment I/O and management. Handles file attachments & web content attachments."""

# Custom validators and word completers live here as well.

import os

import trafilatura
from prompt_toolkit.completion import (
    WordCompleter,
)
from prompt_toolkit.validation import Validator

from localsage.globals import FILE_PATTERN, SESSIONS_DIR, SITE_PATTERN


class FileManager:
    """Handles attachment-related I/O"""

    def __init__(self, session):
        self.session = session

    def _file_validator(self, text: str) -> bool:
        """File validation helper for file_validator()"""
        # Boiled down to two lines, simply validates that a file exists
        text = os.path.abspath(os.path.expanduser(text))
        return os.path.isfile(text)

    def _directory_validator(self, text: str) -> bool:
        text = os.path.abspath(os.path.expanduser(text))
        return os.path.isdir(text)

    def session_completer(self) -> WordCompleter:
        """Session completion helper for the session manager"""
        return WordCompleter(
            [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
            ignore_case=True,
            sentence=True,
        )

    def process_file(self, path: str) -> tuple[bool, int]:
        """Processes a file for attachment"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()

        consumption = self.session.encode(content)
        content = content.replace("```", "ʼʼʼ")
        filename = os.path.basename(path)
        wrapped = f"---\nFile: `{filename}`\n```\n{content}\n```\n---"
        existing = [(i, t, n) for i, t, n in self.get_attachments() if n == filename]
        is_update = False

        # If the file exists already in context, delete it.
        if existing:
            index = existing[-1][0]
            self.session.remove_history(index)
            is_update = True
        # Add the file's content to context, wrapped in Markdown for retrieval
        self.session.append_message("user", wrapped)
        return is_update, consumption

    def process_website(self, url: str) -> int:
        """Processes a website for attachment (uses trafilatura)"""
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise Exception("The website blocked the request or returned no data.")

        content = trafilatura.extract(
            downloaded, include_links=True, include_comments=False
        )

        if not content:
            content = trafilatura.html2txt(downloaded)
        if not content:
            raise Exception("Could not find any readable text on this page.")

        consumption = self.session.encode(content)
        im_a_wrapper = f"---\nWebsite: `{url}`\n{content}\n---"
        self.session.append_message("user", im_a_wrapper)
        return consumption

    def remove_attachment(self, target: int | str) -> str | None:
        """Removes an attachment by name."""
        attachments = self.get_attachments()
        for i, kind, _ in reversed(attachments):
            if target == "[all]":
                self.session.remove_history(i)
                continue
            if target == i:
                self.session.remove_history(i)
                return kind  # For the UI to catch
        return None

    def get_attachments(self) -> list[tuple[int, str, str]]:
        """Retrieves a list of all attachments by utilizing regex."""
        attachments: list[tuple[int, str, str]] = []
        # Iterate through all messages in the conversation history
        for i, msg in enumerate(self.session.history):
            content = msg.get("content")
            if isinstance(content, str):
                match1 = FILE_PATTERN.match(content)
                match2 = SITE_PATTERN.match(content)
                if match1:
                    # Append each attachment to a new structured list
                    attachments.append((i, "file", match1.group(1)))
                if match2:
                    attachments.append((i, "website", match2.group(1)))
        return attachments

    def file_validator(self) -> Validator:
        """Prompt_toolkit file validator"""
        return Validator.from_callable(
            self._file_validator,
            error_message="Invalid file.",
            move_cursor_to_end=True,
        )

    def dir_validator(self) -> Validator:
        """Prompt_toolkit directory validator"""
        return Validator.from_callable(
            self._directory_validator,
            error_message="Invalid directory.",
            move_cursor_to_end=True,
        )
