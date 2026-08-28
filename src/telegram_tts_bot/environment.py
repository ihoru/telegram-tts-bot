"""Optional repository-local environment loading for command entrypoints."""

from pathlib import Path

from dotenv import load_dotenv

REPOSITORY_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_repository_environment() -> bool:
    """Load the source repository's ignored environment without overriding the process."""
    return load_dotenv(dotenv_path=REPOSITORY_ENV_PATH, override=False)
