"""Command interactivity logic lives here."""

import json
import os
import re
import sys
import textwrap

import pyperclip
from keyring import set_password
from keyring.errors import KeyringError
from openai import OpenAI
from prompt_toolkit import prompt
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory

from localsage.globals import (
    COMPLETER_STYLER,
    CONSOLE,
    USER_NAME,
    log_exception,
    retrieve_key,
)


class CLIController:
    """Handles and supports all command input"""

    def __init__(
        self,
        config,
        session,
        filemanager,
        panel,
        ui,
    ):
        self.config = config
        self.ui = ui
        self.session = session
        self.filemanager = filemanager
        self.panel = panel
        self.filepath_history = InMemoryHistory()
        self.interface = None

        # Command dict
        self.commands = {
            "!h": self.spawn_help_chart,
            "!help": self.spawn_help_chart,
            "!s": self.save_session,
            "!save": self.save_session,
            "!l": self.load_session,
            "!load": self.load_session,
            "!a": self.attach_file,
            "!attach": self.attach_file,
            "!attachments": self.list_attachments,
            "!purge": self.purge_attachment,
            "!purge all": self.purge_all_attachments,
            "!consume": self.toggle_consume,
            "!sessions": self.list_sessions,
            "!delete": self.delete_session,
            "!reset": self.reset_session,
            "!sum": self.summarize_session,
            "!summary": self.summarize_session,
            "!config": self.spawn_settings_chart,
            "!clear": CONSOLE.clear,
            "!profile list": self.list_models,
            "!profile add": self.add_model,
            "!profile remove": self.remove_model,
            "!profile switch": self.switch_model,
            "!q": sys.exit,
            "!quit": sys.exit,
            "!ctx": self.set_context_length,
            "!rate": self.set_refresh_rate,
            "!theme": self.set_code_theme,
            "!key": self.set_api_key,
            "!prompt": self.set_system_prompt,
            "!cd": self.change_working_directory,
            "!cp": self.copy_last_snippet,
            "!web": self.read_webpage,
        }

        self.session_prompt = HTML("Enter a session name<seagreen>:</seagreen> ")

    # <~~HELPERS~~>
    def _prompt_wrapper(
        self, prefix, cancel_msg="Canceled.", allow_empty=False, **kwargs
    ) -> str | None:
        """Prompt_toolkit wrapper for validating input."""
        try:
            # **kwargs passes completers, styles, history, etc automatically
            user_input = prompt(prefix, **kwargs)
            stripped = user_input.strip()
            if not stripped and not allow_empty:
                CONSOLE.print("[dim]No input detected.[/dim]\n")
                return None
            return stripped
        except (KeyboardInterrupt, EOFError):
            CONSOLE.print(f"[dim]{cancel_msg}[/dim]\n")
            return None

    def _handle_summary_completion(self, summary_text: str):
        """Callback executed by Chat after streaming finishes successfully."""
        # Reset session, apply summary
        self.session.reset_with_summary(summary_text)

        # Clean up the turn state in Chat
        if self.interface:
            self.interface.reset_turn_state()
            self.session.active_session = ""

        CONSOLE.print("[green]Summarization complete! New session primed.[/green]")
        self.panel.spawn_status_panel(toks=False)

    def handle_input(self, user_input: str) -> bool | None | OpenAI:
        """Parse user input for a command & handle it"""
        cmd = user_input.lower()
        if cmd in self.commands:
            if (
                cmd in ("!q", "!quit", "!sum", "!summarize", "!l", "!load")
                and len(self.session.history) > 1
            ):
                choice = self._prompt_wrapper(
                    HTML("Save first? (<seagreen>y</seagreen>/<ansired>N</ansired>): "),
                    allow_empty=True,
                )
                if choice and choice.lower() in ("y", "yes"):
                    self.save_session()
                elif choice is None:
                    return True
            if cmd in ("!q", "!quit"):
                CONSOLE.print("[yellow]✨ Farewell![/yellow]\n")
            return self.commands[cmd]()
        return False  # No command detected

    def set_interface(self, chat_interface):
        """Setter to inject the Chat/Renderer instance."""
        self.interface = chat_interface

    # <~~CHARTS~~>
    def spawn_help_chart(self):
        """Markdown usage chart."""
        CONSOLE.print(self.ui.help_chart_constructor())
        CONSOLE.print()

    def spawn_settings_chart(self):
        """Markdown settings chart."""
        CONSOLE.print(self.ui.settings_chart_constructor())
        CONSOLE.print()

    # <~~MAIN CONFIG~~>
    def set_system_prompt(self):
        """Sets a new persistent system prompt within the config file."""
        sysprompt = (
            self._prompt_wrapper(
                HTML("Enter a system prompt<seagreen>:</seagreen> "),
                allow_empty=True,
            )
            or ""
        )
        self.config.system_prompt = sysprompt
        self.config.save()
        CONSOLE.print(f"[green]System prompt updated to:[/green] {sysprompt}")
        CONSOLE.print(
            "[dim]Use [cyan]!reset[/cyan] to start a session with the new prompt. Be sure to [cyan]!save[/cyan] first, if desired.[/dim]"
        )
        CONSOLE.print()

    def set_context_length(self):
        """Sets a new persistent context length"""
        ctx = self._prompt_wrapper(
            HTML("Enter a max context length<seagreen>:</seagreen> ")
        )
        if not ctx:
            return
        try:
            value = int(ctx)
            if value <= 0:
                raise ValueError
        except ValueError:
            self.panel.spawn_error_panel(
                "VALUE ERROR", "Please enter a positive number."
            )
            return

        self.config.context_length = value
        self.config.save()
        CONSOLE.print(f"[green]Context length set to:[/green] {value}\n")

    def set_api_key(self) -> OpenAI | None:
        """Allows the user to set an API key. SAFELY stores the user's API key with keyring"""
        new_key = self._prompt_wrapper(HTML("Enter an API key<seagreen>:</seagreen> "))
        if not new_key:
            return
        try:
            # Try to store securely w/ keyring
            set_password("LocalSageAPI", USER_NAME, new_key)
            CONSOLE.print("[green]API key updated.[/green]\n")
        except (KeyringError, ValueError, RuntimeError, OSError) as e:
            self.panel.spawn_error_panel(
                "KEYRING ERROR",
                f"Could not save to your OS keychain: {e}\nUsing key for this session only.",
            )
        return OpenAI(base_url=self.config.endpoint, api_key=new_key)

    def set_refresh_rate(self):
        """Set a new custom refresh rate"""
        rate = self._prompt_wrapper(HTML("Enter a refresh rate<seagreen>:</seagreen> "))
        if not rate:
            return
        try:
            value = int(rate)
            if value <= 3:
                raise ValueError
        except ValueError:
            self.panel.spawn_error_panel(
                "VALUE ERROR", "Please enter a positive number ≥ 4."
            )
            return

        self.config.refresh_rate = value
        self.config.save()
        CONSOLE.print(f"[green]Refresh rate set to:[/green] {value}\n")

    def set_code_theme(self):
        """Allows the user to change out the rich markdown theme"""
        theme = self._prompt_wrapper(
            HTML("Enter a valid theme name<seagreen>:</seagreen> ")
        )
        if not theme:
            return

        self.config.rich_code_theme = theme.lower()
        self.config.save()
        CONSOLE.print(f"[green]Your theme has been set to: [/green]{theme}\n")

    def toggle_consume(self):
        "Toggles reasoning panel consumption on or off"
        self.config.reasoning_panel_consume = not self.config.reasoning_panel_consume
        self.config.save()
        state = "on" if self.config.reasoning_panel_consume else "off"
        color = "green" if self.config.reasoning_panel_consume else "red"
        CONSOLE.print(
            f"Reasoning panel consumption toggled [{color}]{state}[/{color}].\n"
        )

    # <~~MODEL MANAGEMENT~~>
    def list_models(self):
        """List all configured models."""
        CONSOLE.print("[cyan]Configured profiles:[/cyan]")
        for m in self.config.models:
            tag = "(active)" if m["alias"] == self.config.active_model else ""
            CONSOLE.print(f"• {m['alias']} → {m['name']} [{m['endpoint']}] {tag}")
        CONSOLE.print()

    def add_model(self):
        """Interactively add a model profile."""
        alias = self._prompt_wrapper(HTML("Profile name<seagreen>:</seagreen> "))
        if not alias:
            return
        name = self._prompt_wrapper(HTML("Model name<seagreen>:</seagreen> "))
        if not name:
            return
        CONSOLE.print("[yellow]Format:[/yellow] http://ipaddress:port/v1")
        endpoint = self._prompt_wrapper(HTML("API endpoint<seagreen>:</seagreen> "))
        if not endpoint:
            return

        if any(m["alias"] == alias for m in self.config.models):
            CONSOLE.print(f"[dim]Profile[/dim] '{alias}' [dim]already exists.[/dim]\n")
            return

        self.config.models.append(
            {
                "alias": alias,
                "name": name,
                "endpoint": endpoint,
                "api_key": "stored",
            }
        )
        self.config.save()
        CONSOLE.print(f"[green]Profile[/green] '{alias}' [green]added.[/green]\n")

    def remove_model(self):
        """Remove a model profile by alias."""
        self.list_models()
        alias = self._prompt_wrapper(
            HTML("Enter a profile name<seagreen>:</seagreen> ")
        )
        if not alias:
            return

        if alias == self.config.active_model:
            CONSOLE.print("[dim]The active profile cannot be removed.[/dim]\n")
            return

        before = len(self.config.models)
        self.config.models = [m for m in self.config.models if m["alias"] != alias]
        if len(self.config.models) < before:
            self.config.save()
            CONSOLE.print(f"[green]Profile[/green] '{alias}' [green]removed.[/green]\n")
        else:
            CONSOLE.print(f"[dim]No profile found under alias[/dim] '{alias}'.\n")

    def switch_model(self) -> tuple[OpenAI, str] | None:
        """Switch active model profile by alias."""
        self.list_models()
        alias = self._prompt_wrapper(
            HTML("Enter a profile name<seagreen>:</seagreen> ")
        )
        if not alias:
            return

        match = next((m for m in self.config.models if m["alias"] == alias), None)
        if not match:
            CONSOLE.print(f"[dim]No profile found under alias[/dim] '{alias}'.\n")
            return

        self.config.active_model = alias
        self.config.save()
        CONSOLE.print(
            f"[green]Switched to:[/green] {match['name']} "
            f"[dim]{match['endpoint']}[/dim]\n"
        )
        return (
            OpenAI(base_url=match["endpoint"], api_key=retrieve_key()),
            match["name"],
        )

    # <~~SESSION MANAGEMENT~~>
    def save_session(self):
        """Saves a session to a .json file"""
        if self.session.active_session:
            file_name = self.session.active_session
        else:
            file_name = self._prompt_wrapper(self.session_prompt)
            if not file_name:
                return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.save_to_disk(file_path)
            CONSOLE.print(f"[green]Session saved in:[/green] {file_path}\n")
        except Exception as e:
            log_exception(
                e, f"Error in save_session() - file: {os.path.basename(file_path)}"
            )
            self.panel.spawn_error_panel("ERROR SAVING", f"{e}")
            return

    def load_session(self):
        """Loads a session from a .json file"""
        if not self.list_sessions():
            return
        file_name = self._prompt_wrapper(
            self.session_prompt,
            completer=self.filemanager.session_completer(),
            style=COMPLETER_STYLER,
        )
        if not file_name:
            return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.load_from_disk(file_path)
            # Create scrollable history
            if self.interface:
                self.interface.reset_turn_state()
                self.interface.render_history()
            CONSOLE.print(f"[green]Session loaded from:[/green] {file_path}")
            self.panel.spawn_status_panel(toks=False)
        except FileNotFoundError:
            CONSOLE.print(f"[red]No session file found:[/red] {file_path}\n")
            return
        except json.JSONDecodeError:
            CONSOLE.print(f"[red]Corrupted session file:[/red] {file_path}\n")
            return
        except Exception as e:
            log_exception(
                e, f"Error in load_session() — file: {os.path.basename(file_path)}"
            )
            self.panel.spawn_error_panel("ERROR LOADING", f"{e}")

    def delete_session(self):
        """Session deleter. Also lists files for user friendliness."""
        if not self.list_sessions():
            return
        file_name = self._prompt_wrapper(
            self.session_prompt,
            completer=self.session._session_completer(),
            style=COMPLETER_STYLER,
        )
        if not file_name:
            return

        file_path = self.session._json_helper(file_name)
        try:
            self.session.delete_file(file_path)  # Remove the session file
            if self.session.active_session == file_name:
                self.session.active_session = ""
            CONSOLE.print(f"[green]Session deleted:[/green] {file_path}\n")
        except FileNotFoundError:
            CONSOLE.print(f"[red]No session file found:[/red] {file_path}\n")
            return
        except Exception as e:
            log_exception(
                e, f"Error in delete_session() — file: {os.path.basename(file_path)}"
            )
            self.panel.spawn_error_panel("DELETION ERROR", f"{e}")

    def reset_session(self):
        """Simple session resetter."""
        # Start a new conversation history list with the system prompt
        self.session.reset()
        CONSOLE.print("[green]The current session has been reset successfully.[/green]")
        self.panel.spawn_status_panel(toks=False)

    def summarize_session(self):
        """Sets up and triggers summarization"""
        if not self.interface:
            return

        CONSOLE.print("[yellow]Beginning summarization...[/yellow]\n")

        summary_prompt = (
            "Summarize the full conversation for use in a new session."
            "Include the main goals, steps taken, and results achieved."
        )

        # Append the prompt temporarily
        self.session.append_message("user", summary_prompt)
        # Passes a callback to Chat.stream_response
        self.interface.stream_response(callback=self._handle_summary_completion)

    def list_sessions(self):
        """Fetches the session list and displays it."""
        sessions = self.session.find_sessions()

        if not sessions:
            CONSOLE.print("[dim]No saved sessions found.[/dim]\n")
            return

        CONSOLE.print("[cyan]Available sessions:[/cyan]")
        for s in sessions:
            CONSOLE.print(f"• {s}", highlight=False)
        CONSOLE.print()
        return 1

    # <~~FILE MANAGEMENT~~>
    def attach_file(self):
        """Reads a file or directory from disk"""
        path = self._prompt_wrapper(
            HTML("Enter file/directory path<seagreen>:</seagreen> "),
            completer=PathCompleter(expanduser=True),
            validator=self.filemanager.path_validator(),
            validate_while_typing=False,
            style=COMPLETER_STYLER,
            history=self.filepath_history,
        )
        if not path:
            return

        try:
            file = self.filemanager.process_file(path)
            if not file:
                CONSOLE.print(
                    "[dim]Skipped: Source is empty, binary, or contains hidden content.[/dim]\n"
                )
                return
            is_update = file[0]
            consumption = (file[1] / self.config.context_length) * 100
            filename = file[2] or os.path.basename(path)
            if is_update:
                CONSOLE.print(
                    f"{filename} [green]updated successfully.[/green]\n[yellow]Context size:[/yellow] {file[1]}, {consumption:.1f}%"
                )
            else:
                CONSOLE.print(
                    f"{filename} [green]attached successfully.[/green]\n[yellow]Context size:[/yellow] {file[1]}, {consumption:.1f}%"
                )
            if consumption > 50:
                CONSOLE.print(
                    "[dim]Large payload detected! Use [cyan]!purge[/cyan], if needed, to recover context."
                )
            self.panel.spawn_status_panel(toks=False)
        except Exception as e:
            log_exception(e, "Error in process_file()")
            self.panel.spawn_error_panel("ERROR READING FILE", f"{e}")
            return

    def list_attachments(self):
        """List attachments"""
        attachments = self.filemanager.get_attachments()
        if not attachments:
            CONSOLE.print("[dim]No attachments found.[/dim]\n")
            return
        CONSOLE.print("[cyan]Attachments in context:[/cyan]")
        for i, kind, name in attachments:
            CONSOLE.print(
                f"{i}. [sandy_brown]{kind.capitalize()}:[/sandy_brown] {name}"
            )
        CONSOLE.print()

    def purge_attachment(self):
        """Purges an attachment from context and recovers context length"""
        attachments = self.filemanager.get_attachments()
        if not attachments:
            CONSOLE.print("[dim]No attachments found.[/dim]\n")
            return
        CONSOLE.print("[cyan]Attachments in context:[/cyan]")
        for i, kind, name in attachments:
            CONSOLE.print(
                f"{i}. [sandy_brown]{kind.capitalize()}:[/sandy_brown] {name}"
            )
        CONSOLE.print()

        # Prompt for a file to purge
        choice = self._prompt_wrapper(
            HTML("Enter an entry number to purge<seagreen>:</seagreen> ")
        )
        if choice:
            try:
                value = int(choice)
                if value <= 0:
                    CONSOLE.print("[dim]Value must be greater than 0.[/dim]\n")
                    return
            except ValueError:
                CONSOLE.print("[dim]Only valid entry numbers are acceptable.[/dim]\n")
                return
        else:
            return

        # And purge the file from the session
        removed_file = self.filemanager.remove_attachment(value)
        if removed_file:
            CONSOLE.print(
                f"[green]{removed_file.capitalize()} removed from context.[/green]"
            )
            self.panel.spawn_status_panel(toks=False)
        else:
            CONSOLE.print(f"[red]Entry {value} does not exist.[/red]\n")

    def purge_all_attachments(self):
        """Removes all attachments from the active session."""
        self.filemanager.remove_attachment("[all]")
        CONSOLE.print("[cyan]All attachments removed.")
        self.panel.spawn_status_panel(toks=False)

    def change_working_directory(self):
        """Sets a new working directory"""
        path = self._prompt_wrapper(
            HTML("Enter directory path<seagreen>:</seagreen> "),
            completer=PathCompleter(expanduser=True),
            validator=self.filemanager.dir_validator(),
            validate_while_typing=False,
            style=COMPLETER_STYLER,
        )
        if not path:
            return

        try:
            os.chdir(os.path.abspath(os.path.expanduser(path)))
            self.session.append_message(
                "user",
                f"[SYSTEM NOTE: The working directory has changed to {os.getcwd()}. New content is visible in [ENVIRONMENT CONTEXT].]",
            )
            CONSOLE.print(
                f"[green]Working directory is now set to:[/green] [cyan]{path}[/cyan]\n"
            )
        except OSError as e:
            log_exception(e, "Error in change_working_directory()")
            self.panel.spawn_error_panel("ERROR CHANGING DIRECTORY", f"{e}")
            return

    def copy_last_snippet(self):
        """Copies all Markdown code blocks from the last assistant message"""

        assistant_msg = self.session.return_assistant_msg()
        if not assistant_msg:
            CONSOLE.print("[dim]No assistant response found to copy from.[/dim]\n")
            return

        # blocks = re.findall(r"```(?:\w+)?\n(.*?)\n```", assistant_msg, re.DOTALL) | Old regex
        pattern = r"```[^\S\n]*\w*[^\S\n]*\n(.*?)\n[^\S\n]*```"
        blocks = re.findall(pattern, assistant_msg, re.DOTALL)

        if not blocks:
            CONSOLE.print("[dim]No code blocks found in the last response.[/dim]\n")
            return

        code = "\n\n".join(textwrap.dedent(b) for b in blocks).strip()

        try:
            pyperclip.copy(code)
            self.panel.spawn_copy_panel(code)
        except Exception as e:
            log_exception(e, "Error in copy_last_snippet()")
            self.panel.spawn_error_panel(
                "CLIPBOARD ERROR", f"Could not copy to clipboard: {e}"
            )

    def read_webpage(self):
        """Scrapes a web page and appends the contents to history."""
        url = self._prompt_wrapper(
            HTML("Enter a URL<seagreen>:</seagreen> "),
        )
        if not url:
            return
        with CONSOLE.status(
            f"[bold medium_orchid]Reading {url}...[/bold medium_orchid]", spinner="moon"
        ):
            try:
                site = self.filemanager.process_website(url)
                consumption = (site / self.config.context_length) * 100
            except Exception as e:
                CONSOLE.print(f"[red]Failed to fetch URL:[/red] {e}\n")
                return
            CONSOLE.print(
                f"[green]Successfully ingested[/green] {url}\n[yellow]Context size:[/yellow] {site}, {consumption:.1f}%"
            )
            self.panel.spawn_status_panel(toks=False)
