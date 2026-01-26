"""Attachment I/O and management. Handles file attachments & web content attachments."""

# Custom validators and word completers live here as well.

import os

import trafilatura
from prompt_toolkit.completion import (
    WordCompleter,
)
from prompt_toolkit.validation import Validator

from localsage.globals import (
    DIR_PATTERN,
    FILE_PATTERN,
    RESTRICTED_FILES,
    SESSIONS_DIR,
    SITE_PATTERN,
)


class FileManager:
    """Handles attachment-related I/O"""

    def __init__(self, session):
        self.session = session

    def session_completer(self) -> WordCompleter:
        """Session completion helper for the session manager"""
        return WordCompleter(
            [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
            ignore_case=True,
            sentence=True,
        )

    def process_file(self, path: str) -> tuple[bool, int, str] | None:
        """Processes a file or directory for attachment"""
        content_blocks: list[str] = []
        filelist: list[str] = []

        path = os.path.abspath(os.path.expanduser(path))
        basename = os.path.basename(path)

        def read_file(src: str) -> str:
            try:
                with open(src, "r", encoding="utf-8") as f:
                    return f.read().replace("```", "'''")
            except UnicodeDecodeError:
                with open(src, "r", encoding="latin-1") as f:
                    return f.read().replace("```", "'''")

        if os.path.isdir(path):
            with os.scandir(path) as entries:
                for file in entries:
                    if (
                        file.is_file()
                        and not file.name.startswith(".")
                        and not file.name.endswith(RESTRICTED_FILES)
                    ):
                        filelist.append(file.name)
                        content_blocks.append(
                            f"File: `{file.name}`\n```\n{read_file(file.path)}\n```"
                        )
            if not filelist:
                return
            formatted = ", ".join(filelist)
            content = "\n\n".join(content_blocks)
            wrapped = (
                f"---\nDirectory: `{basename}`\nFiles: `{formatted}`\n\n{content}\n---"
            )
        elif os.path.isfile(path) and not path.endswith(RESTRICTED_FILES):
            formatted = ""
            wrapped = f"---\nFile: `{basename}`\n```\n{read_file(path)}\n```\n---"
        else:
            return

        consumption = self.session.encode(wrapped)

        # If the file exists already in context, delete it.
        existing = [(i, t, n) for i, t, n in self.get_attachments() if n == basename]
        if existing:
            self.session.remove_history(existing[-1][0])

        self.session.append_message("user", wrapped)
        return bool(existing), consumption, formatted

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
                match3 = DIR_PATTERN.match(content)
                if match1:
                    attachments.append((i, "file", match1.group(1)))
                if match2:
                    attachments.append((i, "website", match2.group(1)))
                if match3:
                    attachments.append((i, "directory", match3.group(1)))
        return attachments

    def path_validator(self) -> Validator:
        """Prompt_toolkit file validator"""

        def _validator(text: str) -> bool:
            """Path validation helper for path_validator()"""
            text = os.path.abspath(os.path.expanduser(text))
            return os.path.isfile(text) or os.path.isdir(text)

        return Validator.from_callable(
            _validator,
            error_message="Invalid path.",
            move_cursor_to_end=True,
        )

    def dir_validator(self) -> Validator:
        """Prompt_toolkit directory validator"""

        def _dir_validator(text: str) -> bool:
            """Directory validation helper for dir_validator()"""
            text = os.path.abspath(os.path.expanduser(text))
            return os.path.isdir(text)

        return Validator.from_callable(
            _dir_validator,
            error_message="Invalid directory.",
            move_cursor_to_end=True,
        )
