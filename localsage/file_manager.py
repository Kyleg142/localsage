"""Attachment I/O and management. Handles file attachments & web content attachments."""

# Custom validators and word completers live here as well.

import os
import re
from urllib.parse import urlparse

from prompt_toolkit.completion import (
    WordCompleter,
)
from prompt_toolkit.validation import Validator

from localsage.globals import (
    FILE_PATTERN,
    RESTRICTED_FILES,
    SESSIONS_DIR,
    SITE_PATTERN,
    SPECIAL_FILES,
    WEB_FILES,
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

        def remove_existing(name: str) -> bool:
            attachments = self.get_attachments()
            existing = [(i, t, n) for i, t, n in attachments if n == name]
            if existing:
                self.session.remove_history(existing[-1][0])
                return True
            return False

        def read_file(src: str) -> str:
            try:
                with open(src, "r", encoding="utf-8") as f:
                    return f.read().replace("```", "'''")
            except UnicodeDecodeError:
                with open(src, "r", encoding="latin-1") as f:
                    return f.read().replace("```", "'''")

        def file_wrapper(name: str, path: str) -> str:
            return f"---\nFile: `{name}`\n```\n{path}\n```\n---"

        consumption: int = 0
        filelist: list[str] = []
        existing: bool = False

        path = os.path.abspath(os.path.expanduser(path))
        basename = os.path.basename(path)

        if os.path.isdir(path):
            with os.scandir(path) as entries:
                for file in entries:
                    if (
                        file.is_file()
                        and not file.name.startswith(".")
                        and not file.name.endswith(RESTRICTED_FILES)
                    ):
                        try:
                            wrapped = file_wrapper(file.name, read_file(file.path))
                            existing = remove_existing(file.name)
                            self.session.append_message("user", wrapped)
                            consumption += self.session.encode(wrapped)
                            filelist.append(file.name)
                        except (PermissionError, FileNotFoundError):
                            continue
            if not filelist:
                return
            formatted = ", ".join(filelist)

        elif os.path.isfile(path) and not path.endswith(RESTRICTED_FILES):
            formatted = ""
            try:
                wrapped = file_wrapper(basename, read_file(path))
                existing = remove_existing(basename)
                self.session.append_message("user", wrapped)
                consumption = self.session.encode(wrapped)
            except PermissionError:
                raise PermissionError(f"Permission Denied: {path}")

        else:
            return

        return existing, consumption, formatted

    def process_website(self, url: str) -> int:
        """Processes a website for attachment (uses trafilatura)"""
        import trafilatura

        def normalize_url(url: str) -> str:
            """Converts a github, gitlab, or pastebin URL to it's raw alternative"""
            parsed = urlparse(url.strip())
            u = url.strip()
            if parsed.netloc == "github.com" and "/blob/" in parsed.path:
                return u.replace("github.com", "raw.githubusercontent.com").replace(
                    "/blob/", "/", 1
                )
            if parsed.netloc == "gitlab.com" and "/blob/" in parsed.path:
                return u.replace("/blob/", "/raw/", 1)
            if parsed.netloc == "pastebin.com" and not parsed.path.startswith("/raw/"):
                paste_id = parsed.path.strip("/").split("/")[-1]
                return f"https://pastebin.com/raw/{paste_id}"
            return u

        def scrub_content(content: str) -> str:
            """Scrubs junk out of received web content"""
            # Regex to detect junk HTML noise for disposal
            tags_to_nuke = (
                r"<(script|style|svg|noscript|iframe|form)\b[^>]*>([\s\S]*?)<\/\1>"
            )
            comments = r"<!--[\s\S]*?-->"
            content = re.sub(tags_to_nuke, "", content, flags=re.IGNORECASE)
            content = re.sub(comments, "", content, flags=re.IGNORECASE)
            return content.strip()

        original_url = url
        url = normalize_url(url)
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise Exception("The website blocked the request or returned no data.")
        parsed = urlparse(url)

        is_html = not (
            parsed.netloc == "raw.githubusercontent.com"
            or "/raw/" in parsed.path
            or url.lower().endswith(WEB_FILES)
            or url.lower().split("/")[-1] in SPECIAL_FILES
        )

        if is_html:
            cleaned_html = scrub_content(downloaded)
            content = trafilatura.extract(
                cleaned_html, include_links=True, include_comments=False
            )
            if not content:
                content = trafilatura.html2txt(cleaned_html)
        else:
            content = downloaded

        # Dip out if no site content was found
        if not content or not content.strip():
            raise Exception("Could not find any readable text on this page.")

        im_a_wrapper = f"---\nWebsite: `{original_url}`\n{content}\n---"
        consumption = self.session.encode(im_a_wrapper)
        self.session.append_message("user", im_a_wrapper)
        return consumption

    def process_file_size(self, path: str) -> int:
        size: int = 0
        if os.path.isfile(path) and not path.endswith(RESTRICTED_FILES):
            try:
                size = os.path.getsize(path)
            except PermissionError:
                raise PermissionError(f"Permission Denied: {path}")
        elif os.path.isdir(path):
            with os.scandir(path) as entries:
                for file in entries:
                    try:
                        if (
                            file.is_file()
                            and not file.name.startswith(".")
                            and not file.name.endswith(RESTRICTED_FILES)
                        ):
                            size += file.stat().st_size
                    except (PermissionError, FileNotFoundError):
                        continue
        return size

    def remove_attachment(self, target: int | str) -> str | None:
        """Removes an attachment by index."""
        attachments = self.get_attachments()
        purge: bool = True
        for i, kind, _ in reversed(attachments):
            if target == "[all]":
                purge = self.session.remove_history(i)
                if not purge:
                    return None
                continue
            if target == i:
                purge = self.session.remove_history(i)
                if not purge:
                    return None
                return kind  # For the UI to catch
        return "pass"

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
                    attachments.append((i, "file", match1.group(1)))
                if match2:
                    attachments.append((i, "website", match2.group(1)))
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
