"""Global functions and variables, used across various modules."""

import getpass
import logging
import os
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler

import keyring
from keyring import get_password
from keyring.backends import null
from platformdirs import user_data_dir
from prompt_toolkit import prompt
from prompt_toolkit.completion import (
    WordCompleter,
)
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.spinner import Spinner

# Default directories and system details
APP_DIR = user_data_dir("LocalSage")
CONFIG_DIR = os.path.join(APP_DIR, "config")
SESSIONS_DIR = os.path.join(APP_DIR, "sessions")
LOG_DIR = os.path.join(APP_DIR, "logs")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
USER_NAME = getpass.getuser()

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Compiled regex used in the context management system
# Alternative, allows whitespace: ^---\s*File:\s*(.+?)
FILE_PATTERN = re.compile(r"^---\nFile: `(.*?)`", re.MULTILINE)
DIR_PATTERN = re.compile(r"^---\nDirectory: `(.*?)`", re.MULTILINE)
SITE_PATTERN = re.compile(r"^---\nWebsite: `(.*?)`", re.MULTILINE)

# Restricted file types that are not compatible with text-based assistants
RESTRICTED_FILES = (
    # Images
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".ico",
    ".tiff",
    ".webp",
    ".heic",
    ".raw",
    ".psd",
    ".ai",
    ".xcf",
    ".svg",  # svg is XML, but it is awful to feed to an LLM, too much noise
    # Audio/Video
    ".mp4",
    ".mkv",
    ".mov",
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".m4a",
    ".webm",
    ".avi",
    ".wmv",
    ".wma",
    # Archives & Compressed
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".iso",
    ".jar",
    ".tgz",
    ".bz2",
    ".xz",
    ".cab",
    ".z",
    ".lz4",
    ".zst",
    # Installers & Packages
    ".dmg",
    ".pkg",
    ".deb",
    ".rpm",
    ".msi",
    ".msix",
    ".apk",
    ".war",
    ".ear",
    # Executables & Compiled Bytecode
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".o",
    ".obj",
    ".pyc",
    ".pyo",
    ".pyd",
    ".class",
    ".dylib",
    ".elf",
    ".wasm",
    ".node",
    # AI & Big Data
    ".onnx",
    ".tflite",
    ".pth",
    ".h5",
    ".ckpt",
    ".pt",
    ".safetensors",
    ".parquet",
    ".arrow",
    ".npy",
    ".npz",
    ".pickle",
    ".pkl",
    # Documents & Ebooks
    ".pdf",
    ".epub",
    ".mobi",
    ".djvu",
    # Zipped XML
    ".docx",
    ".xlsx",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
    # Legacy Extensions
    ".doc",
    ".xls",
    ".ppt",
    # Fonts
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
    ".cur",
    ".ani",
    # Databases & Virtualization
    ".db",
    ".sqlite",
    ".sqlite3",
    ".mdb",
    ".accdb",
    ".vdi",
    ".vmdk",
    ".qcow2",
    ".ova",
    ".img",
    # System Metadata & Logs
    ".ds_store",
    "thumbs.db",
    ".swp",
    ".journal",  # Systemd binary logs
)

# Filter for attaching text files via html
WEB_FILES = (
    # Web & Frontend
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".astro",
    ".graphql",
    ".gql",
    # Systems & Logic
    ".py",
    ".pyi",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cc",
    ".hh",
    ".cs",
    ".java",
    ".rb",
    ".php",
    ".swift",
    ".m",
    ".mm",
    ".kt",
    ".kts",
    ".dart",
    ".rs",
    ".go",
    ".zig",
    ".lua",
    ".pl",
    ".pm",
    ".hs",
    ".erl",
    ".ex",
    ".exs",
    ".sql",
    # Shell & Scripts
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".awk",
    # Config & Data
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".env",
    ".xml",
    ".csv",
    ".tsv",
    ".proto",
    ".tf",
    ".tfvars",
    # Documentation & Meta
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".log",
    ".diff",
    ".patch",
    ".gitignore",
    ".dockerignore",
    ".editorconfig",
)

SPECIAL_FILES = ("dockerfile", "makefile", "procfile", "gemfile", "license")


# Terminal integration
CONSOLE = Console()

# Main prompt prefix
PROMPT_PREFIX = HTML("<seagreen>󰅂 </seagreen>")

# Dark style for all prompt_toolkit completers
COMPLETER_STYLER = Style.from_dict(
    {
        # Completions
        "completion-menu.completion": "bg:#202020 #ffffff",
        "completion-menu.completion.current": "bg:#024a1a #000000",  # 2E8B57
        # Tooltips
        "completion-menu.meta.completion": "bg:#202020 #aaaaaa",
        "completion-menu.meta.completion.current": "bg:#024a1a #000000",
    }
)

# Main prompt command completer
COMMAND_COMPLETER = WordCompleter(
    [
        "!a",
        "!attach",
        "!attachments",
        "!cd",
        "!clear",
        "!config",
        "!consume",
        "!cp",
        "!ctx",
        "!delete",
        "!h",
        "!help",
        "!key",
        "!l",
        "!load",
        "!profile add",
        "!profile list",
        "!profile remove",
        "!profile switch",
        "!prompt",
        "!purge",
        "!purge all",
        "!q",
        "!quit",
        "!rate",
        "!reset",
        "!s",
        "!save",
        "!sessions",
        "!sum",
        "!summary",
        "!theme",
        "!web",
    ],
    match_middle=True,
    WORD=True,
)

# In-memory history for the root prompt, must mutate
main_history = InMemoryHistory()


def init_logger():
    """Initializes the logging system."""
    date_str = datetime.now().strftime("%Y%m%d")
    # Output example: localsage_20251109.log
    log_path = os.path.join(LOG_DIR, f"localsage_{date_str}.log")
    # Max of 3 backups, max size of 1MB
    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[handler],
    )


def log_exception(e: Exception, context: str = ""):
    """Creates a full formatted traceback string and writes it to a log file"""
    import traceback

    # Format the traceback (exception class, exception instance, traceback object)
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    # Add optional context provided by error catchers ('except Exception as e:' blocks)
    msg = f"{context}\n{tb}" if context else tb
    logging.error(msg)


def setup_keyring_backend():
    """Safely detects a keyring backend."""
    try:
        keyring.get_keyring()
    except Exception as e:
        keyring.set_keyring(null.Keyring())
        logging.error(
            f"Keyring backend failed. Falling back to NullBackend. Error: {e}"
        )


def retrieve_key() -> str:
    """
    Attempts to retrieve a stored API key.\n
    Prio: OPENAI_API_KEY env variable -> OS keyring entry -> Dummy key
    """
    api_key = ""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
    except Exception:
        pass
    if not api_key:
        try:
            api_key = get_password("LocalSageAPI", USER_NAME)
        except Exception:
            pass
    if not api_key:
        api_key = "dummy-key"
    return api_key


def spinner_constructor(content: str) -> Spinner:
    """Returns a themed Rich spinner."""
    return Spinner(
        "moon",
        text=f"[bold medium_orchid]{content}[/bold medium_orchid]",
    )


def root_prompt() -> str:
    """Returns the root prompt"""
    return prompt(
        PROMPT_PREFIX,
        completer=COMMAND_COMPLETER,
        style=COMPLETER_STYLER,
        complete_while_typing=False,
        history=main_history,
    )
