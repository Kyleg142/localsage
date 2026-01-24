"""Builds and spawns UI objects. UIConstructor and GlobalPanels live here."""

import os
import textwrap

from rich import box
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from localsage import __version__
from localsage.globals import CONFIG_FILE, CONSOLE, LOG_DIR, SESSIONS_DIR
from localsage.math_sanitizer import sanitize_math_safe


class UIConstructor:
    """Constructs and returns various UI objects"""

    def __init__(self, config, session):
        self.config = config
        self.session = session

    def reasoning_panel_constructor(self) -> Panel:
        return Panel(
            "",
            title=Text("🧠 Reasoning", style="bold yellow"),
            title_align="left",
            border_style="yellow",
            style="#b0b0b0 italic",
            width=None,
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def response_panel_constructor(self) -> Panel:
        return Panel(
            "",
            title=Text("💬 Response", style="bold green"),
            title_align="left",
            border_style="green",
            style="default",
            width=None,
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def user_panel_constructor(self, content: str) -> Panel:
        return Panel(
            content,
            box=box.HORIZONTALS,
            padding=(0, 0),
            title=Text("🌐 You", style="bold blue"),
            title_align="left",
            border_style="blue",
            style="default",
        )

    def assistant_panel_constructor(self, content: str) -> Panel:
        return Panel(
            Markdown(
                sanitize_math_safe(content), code_theme=self.config.rich_code_theme
            ),
            title=Text("💬 Response", style="bold green"),
            title_align="left",
            border_style="green",
            style="default",
            width=None,
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def status_panel_constructor(self, toks=True) -> Panel:
        turns = self.session.count_turns()
        tokens = self.session.count_tokens()
        throughput = 0
        if isinstance(tokens, tuple):
            context = tokens[0]
            throughput = tokens[1]
        else:
            context = tokens
        context_percentage = round((context / self.config.context_length) * 100, 1)

        # Colorize context percentage based on context consumption
        context_color: str = "dim"
        if context_percentage >= 50 and context_percentage < 80:
            context_color = "yellow"
        elif context_percentage >= 80:
            context_color = "red"

        # Status panel content
        status_text = Text.assemble(
            (" ", "cyan"),
            ("Context: "),
            (f"{context_percentage}%", f"{context_color}"),
            (" | "),
            (f"Turn: {turns}"),
        )
        if throughput and toks:
            status_text.append(f" | Tk/s: {throughput:.1f}")
        return Panel(
            status_text,
            border_style="dim",
            style="dim",
            expand=False,
        )

    def intro_panel_constructor(self) -> Panel:
        intro_text = Text.assemble(
            ("Model: ", "bold sandy_brown"),
            (f"{self.config.model_name}"),
            ("\nProfile: ", "bold sandy_brown"),
            (f"{self.config.alias_name}"),
            ("\nSystem Prompt: ", "bold sandy_brown"),
            (f"{self.config.system_prompt}", "italic"),
            ("\nWorking Directory: ", "bold sandy_brown"),
            (f"{os.getcwd()}"),
        )
        return Panel(
            intro_text,
            title=Text(f"🔮 Local Sage {__version__}", "bold medium_orchid"),
            title_align="left",
            border_style="medium_orchid",
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def error_panel_constructor(self, error: str, exception: str) -> Panel:
        return Panel(
            exception,
            title=Text(f"❌ {error}", style="bold red"),
            title_align="left",
            border_style="red",
            expand=False,
        )

    def copy_panel_constructor(self, blocks: str) -> Panel:
        wrapped = f"### The following code has been copied to your clipboard\n```\n{blocks}\n```"
        return Panel(
            Markdown(wrapped, code_theme=self.config.rich_code_theme),
            title=Text("📋 Clipboard Sync", style="bold orange1"),
            title_align="left",
            border_style="orange1",
            box=box.HORIZONTALS,
            padding=(0, 0),
        )

    def help_chart_constructor(self) -> Markdown:
        return Markdown(
            textwrap.dedent("""
            | **Profile Management** | *Manage multiple models & API endpoints* |
            | --- | ----------- |
            | `!profile add` | Add a new model profile. Prompts for alias, model name, and **API endpoint**. |
            | `!profile remove` | Remove an existing profile. |
            | `!profile list` | List configured profiles. |
            | `!profile switch` | Switch between profiles. |

            | **Configuration** | *Main configuration commands* |
            | --- | ----------- |
            | `!config` | Display your current configuration settings and default directories. |
            | `!consume` | Toggle Reasoning panel consumption.  |
            | `!ctx` | Set maximum context length (for CLI functionality). |
            | `!key` | Set an API key, if needed. Your API key is stored in your OS keychain. |
            | `!prompt` | Set a new system prompt. Takes effect on your next session. |
            | `!rate` | Set the current refresh rate (default is 30). Higher refresh rate = higher CPU usage. |
            | `!theme` | Change your Markdown theme. Built-in themes can be found at https://pygments.org/styles/ |

            | **Session Management** | *Session management commands* |
            | --- | ----------- |
            | `!s` or `!save` | Save the current session. |
            | `!l` or `!load` | Load a saved session, including a scrollable conversation history. |
            | `!sum` or `!summary` | Prompt your model for summarization and start a fresh session with the summary. |
            | `!sessions` | List all saved sessions. |
            | `!reset` | Reset for a fresh session. |
            | `!delete` | Delete a saved session. |
            | `!clear` | Clear the terminal window. |
            | `!q` or `!quit` | Exit Local Sage. |
            | | |
            | `Ctrl + C` | Abort mid-stream, reset the turn, and return to the root prompt. Also acts as an immediate exit. |
            | **WARNING:** | Using `Ctrl + C` as an immediate exit does not trigger an autosave! |

            | **Context Management** | *Manage context & attachments* |
            | --- | ----------- |
            | `!a` or `!attach` | Attaches a file to the current session. |
            | `!web` | Scrapes a website, and attaches the contents to the current session. |
            | `!attachments` | List all current attachments. |
            | `!purge` | Choose a specific attachment and purge it from the session. Recovers context length. |
            | `!purge all` | Purges all attachments from the current session. |
            | `!cd` | Change the current working directory. |
            | `!cp` | Copy all code blocks from the last response. |
            | | |
            | **FILE TYPES:** | All text-based file types are acceptable. |
            | **NOTE:** | If you ever attach a problematic file, `!purge` can be used to rescue the session. |
            """)
        )

    def settings_chart_constructor(self) -> Markdown:
        return Markdown(
            textwrap.dedent(f"""
            | **Current Settings** | *Your current persistent settings* |
            | --- | ----------- |
            | **Profile**: | *{self.config.alias_name}* |
            | | |
            | **Model Name**: | *{self.config.model_name}* |
            | | |
            | **System Prompt**: | *{self.config.system_prompt}* |
            | | |
            | **Context Length**: | *{self.config.context_length}* |
            | | |
            | **Refresh Rate**: | *{self.config.refresh_rate}* |
            | | |
            | **Markdown Theme**: | *{self.config.rich_code_theme}* |
            - Your configuration file is located at: `{CONFIG_FILE}`
            - Your session files are located at:     `{SESSIONS_DIR}`
            - Your error logs are located at:        `{LOG_DIR}`
            - The current working directory is:      `{os.getcwd()}`
            """)
        )


class GlobalPanels:
    """Global panel spawner"""

    def __init__(self, session, config, ui: UIConstructor):
        self.session = session
        self.config = config
        self.ui: UIConstructor = ui

    def spawn_intro_panel(self):
        """Simple welcome panel, prints on application launch."""
        CONSOLE.print(self.ui.intro_panel_constructor())
        CONSOLE.print(Markdown("Type `!h` for a list of commands."))
        CONSOLE.print()

    def spawn_status_panel(self, toks=True):
        """Prints a status panel."""
        # Status panel constructor
        CONSOLE.print(self.ui.status_panel_constructor(toks))
        CONSOLE.print()

    def spawn_error_panel(self, error: str, exception: str):
        """Error panel template for Local Sage, used in Chat() and main()"""
        CONSOLE.print(self.ui.error_panel_constructor(error, exception))
        CONSOLE.print()

    def spawn_user_panel(self, content: str):
        """Spawns the user panel."""
        CONSOLE.print()
        CONSOLE.print(self.ui.user_panel_constructor(content))
        CONSOLE.print()

    def spawn_assistant_panel(self, content: str):
        """Spawns the Response panel - for a scrollable history."""
        CONSOLE.print(self.ui.assistant_panel_constructor(content))

    def spawn_copy_panel(self, blocks: str):
        CONSOLE.print(self.ui.copy_panel_constructor(blocks))
        CONSOLE.print()
