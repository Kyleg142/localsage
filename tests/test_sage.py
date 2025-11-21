"""
A 'mock and drive' test for sage.py.

- Imitates key variables
- Saves and loads the config file
- Initializes the Chat() class
- Starts the application and exits
"""

from unittest.mock import patch

import pytest

from localsage import sage

# 1. Configuration Tests


def test_config_defaults(tmp_path):
    """
    Verify Config initializes with correct defaults.
    Config file location is patched to a temp dir so we don't overwrite real settings.
    """
    # Create a fake config path in a temporary directory
    fake_config_dir = tmp_path / "config"
    fake_config_dir.mkdir()
    fake_config_file = fake_config_dir / "settings.json"

    # Patch the CONFIG_FILE variable in the sage module
    with patch("localsage.sage.CONFIG_FILE", str(fake_config_file)):
        cfg = sage.Config()

        # Assert defaults
        assert cfg.active_model == "default"
        assert cfg.context_length == 131072
        assert cfg.refresh_rate == 30
        assert cfg.model_name == "Sage"


def test_config_save_load(tmp_path):
    """Verify the CLI save and load settings from disk."""
    fake_config_file = tmp_path / "settings.json"

    with patch("localsage.sage.CONFIG_FILE", str(fake_config_file)):
        # 1. Create and Save
        cfg = sage.Config()
        cfg.active_model = "test_alias"
        cfg.save()

        # 2. Load into new object
        cfg_loaded = sage.Config()
        cfg_loaded.load()

        assert cfg_loaded.active_model == "test_alias"


# 2. CLI Initialization Test (The "Smoke Test")


@patch("localsage.sage.OpenAI")
@patch("localsage.sage.get_password")
def test_chat_initialization(mock_get_pass, mock_openai):
    """
    Verify the Chat class initializes without crashing.
    We must mock OpenAI and keyring so it doesn't hit the network or OS keychain.
    """
    # Setup Mocks
    mock_get_pass.return_value = "fake-api-key"

    # Create a dummy config
    cfg = sage.Config()

    # Initialize Chat
    session = sage.Chat(cfg)

    # Assertions
    assert session.client is not None
    # Verify it tried to get the password for the current user
    mock_get_pass.assert_called_with("LocalSageAPI", sage.USER_NAME)


# 3. Main Application Loop (The "End-to-End" Test)


@patch("localsage.sage.prompt")  # Mock the user input
@patch("localsage.sage.OpenAI")  # Mock the API
@patch("localsage.sage.get_password")  # Mock the keychain
@patch("localsage.sage.Console")  # Mock Rich Console to silence output
def test_application_startup_and_quit(
    mock_console, mock_get_pass, mock_openai, mock_prompt
):
    """
    The 'Holy Grail' test.
    1. Starts sage.py.
    2. Mocks the user typing '!q' immediately.
    3. Verifies the app shuts down cleanly without errors.
    """
    # 1. Setup dependencies
    mock_get_pass.return_value = "fake-api-key"

    # 2. Setup the input stream
    # The app calls prompt() inside a loop.
    # First call: return "!q" to quit.
    mock_prompt.return_value = "!q"

    # 3. Run the main entry point
    # sage.py doesn't actually use SystemExit, but it is here for redundancy
    try:
        sage.main()
    except SystemExit as e:
        # If your app called sys.exit(0), that's a success.
        # If it called sys.exit(1), it's a failure.
        assert e.code == 0
    except Exception as e:
        pytest.fail(f"App crashed during startup: {e}")

    # 4. Verification
    # Did we actually ask for input?
    mock_prompt.assert_called()
