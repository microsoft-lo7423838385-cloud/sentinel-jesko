import os
import sys

# --- Add project root to the Python path to allow imports ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
# -------------------------------------------------------------

from settings import settings, AppSettings

def test_settings_are_loaded():
    """
    Tests that the global 'settings' object is an instance of our main
    AppSettings model, proving that the file was read and parsed successfully.
    """
    assert isinstance(settings, AppSettings)

def test_general_settings_are_correct():
    """
    Tests a few specific values from the [GENERAL] section of the config
    to ensure they are loaded with the correct type.
    """
    assert settings.general.sending_method == "smtp"
    assert isinstance(settings.general.max_workers, int)
    assert settings.general.max_workers == 7

def test_email_subjects_is_a_list():
    """Tests that the '::' separated subject string is correctly parsed into a list."""
    assert isinstance(settings.email.email_subjects, list)
    assert len(settings.email.email_subjects) > 1
    assert settings.email.email_subjects[0] == "Your document is ready"