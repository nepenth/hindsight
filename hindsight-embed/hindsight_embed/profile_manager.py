"""Profile management for hindsight-embed.

Handles creation, deletion, and management of configuration profiles.
Each profile has its own config, daemon lock, log file, and port.
"""

import fcntl
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

# Configuration paths
CONFIG_DIR = Path.home() / ".hindsight"
PROFILES_DIR = CONFIG_DIR / "profiles"
ACTIVE_PROFILE_FILE = CONFIG_DIR / "active_profile"

# Port allocation
DEFAULT_PORT = 8888


@dataclass
class ProfilePaths:
    """Paths and port for a profile."""

    config: Path
    lock: Path
    log: Path
    port: int


@dataclass
class ProfileInfo:
    """Profile information including metadata."""

    name: str
    port: int
    created_at: str
    last_used: Optional[str] = None
    is_active: bool = False
    daemon_running: bool = False


class ProfileManager:
    """Manages configuration profiles for hindsight-embed."""

    def __init__(self):
        """Initialize the profile manager."""
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure profile directories exist."""
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[ProfileInfo]:
        """List all profiles with their status.

        Returns:
            List of ProfileInfo objects with daemon status.
        """
        active_profile = self.get_active_profile()
        profiles = []

        # Add default profile if config exists
        default_config = CONFIG_DIR / "embed"
        if default_config.exists():
            stat = default_config.stat()
            profiles.append(
                ProfileInfo(
                    name="",  # Empty name = default
                    port=DEFAULT_PORT,
                    created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
                    last_used=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    is_active=active_profile == "",
                    daemon_running=self._check_daemon_running(DEFAULT_PORT),
                )
            )

        # Add named profiles by listing .env files
        if PROFILES_DIR.exists():
            for env_file in sorted(PROFILES_DIR.glob("*.env")):
                name = env_file.stem
                port = self._read_port_from_env(env_file)
                if port is None:
                    continue  # Skip profiles without PORT

                stat = env_file.stat()
                profiles.append(
                    ProfileInfo(
                        name=name,
                        port=port,
                        created_at=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
                        last_used=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        is_active=active_profile == name,
                        daemon_running=self._check_daemon_running(port),
                    )
                )

        return sorted(profiles, key=lambda p: (p.name != "", p.name))

    def profile_exists(self, name: str) -> bool:
        """Check if a profile exists.

        Args:
            name: Profile name (empty string for default).

        Returns:
            True if profile exists.
        """
        if not name:
            # Default profile exists if config file exists
            return (CONFIG_DIR / "embed").exists()

        # Named profile exists if config file exists
        config_path = PROFILES_DIR / f"{name}.env"
        return config_path.exists()

    def get_profile(self, name: str) -> Optional[ProfileInfo]:
        """Get profile information.

        Args:
            name: Profile name (empty string for default).

        Returns:
            ProfileInfo if profile exists, None otherwise.
        """
        profiles = self.list_profiles()
        for profile in profiles:
            if profile.name == name:
                return profile
        return None

    def create_profile(self, name: str, port: int, config: dict[str, str]):
        """Create or update a profile.

        Args:
            name: Profile name.
            port: Port number for the daemon.
            config: Configuration dict (KEY=VALUE pairs).

        Raises:
            ValueError: If profile name is invalid or port is already in use.
        """
        if not name:
            raise ValueError("Profile name cannot be empty")

        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid profile name '{name}'. Use alphanumeric chars, hyphens, and underscores.")

        if port < 1024 or port > 65535:
            raise ValueError(f"Invalid port {port}. Must be between 1024-65535.")

        # Ensure profile directory exists
        self._ensure_directories()

        # Check if port is already in use by another profile
        for profile in self.list_profiles():
            if profile.name != name and profile.port == port:
                raise ValueError(f"Port {port} is already in use by profile '{profile.name}'")

        # Write config file with PORT as first line
        config_path = PROFILES_DIR / f"{name}.env"
        config_lines = [f"PORT={port}"] + [f"{key}={value}" for key, value in config.items()]
        config_path.write_text("\n".join(config_lines) + "\n")

    def delete_profile(self, name: str):
        """Delete a profile.

        Args:
            name: Profile name (empty string for default).

        Raises:
            ValueError: If profile doesn't exist.
        """
        if not self.profile_exists(name):
            raise ValueError(f"Profile '{name or 'default'}' does not exist")

        if not name:
            # Delete default profile
            config_files = [CONFIG_DIR / "embed", CONFIG_DIR / "config.env"]
            for config_file in config_files:
                if config_file.exists():
                    config_file.unlink()

            lock_file = CONFIG_DIR / "daemon.lock"
            if lock_file.exists():
                lock_file.unlink()

            log_file = CONFIG_DIR / "daemon.log"
            if log_file.exists():
                log_file.unlink()
        else:
            # Delete named profile
            config_path = PROFILES_DIR / f"{name}.env"
            if config_path.exists():
                config_path.unlink()

            lock_path = PROFILES_DIR / f"{name}.lock"
            if lock_path.exists():
                lock_path.unlink()

            log_path = PROFILES_DIR / f"{name}.log"
            if log_path.exists():
                log_path.unlink()

        # Clear active profile if it was deleted
        if self.get_active_profile() == name:
            self.set_active_profile(None)

    def set_active_profile(self, name: Optional[str]):
        """Set the active profile.

        Args:
            name: Profile name to activate, or None to clear.

        Raises:
            ValueError: If profile doesn't exist.
        """
        if name and not self.profile_exists(name):
            raise ValueError(f"Profile '{name}' does not exist")

        if name:
            ACTIVE_PROFILE_FILE.write_text(name)
        else:
            # Clear active profile
            if ACTIVE_PROFILE_FILE.exists():
                ACTIVE_PROFILE_FILE.unlink()

    def get_active_profile(self) -> str:
        """Get the currently active profile name.

        Returns:
            Profile name, or empty string if no active profile.
        """
        if ACTIVE_PROFILE_FILE.exists():
            return ACTIVE_PROFILE_FILE.read_text().strip()
        return ""

    def resolve_profile_paths(self, name: str) -> ProfilePaths:
        """Resolve paths for a profile.

        Args:
            name: Profile name (empty string for default).

        Returns:
            ProfilePaths with config, lock, log, and port.
        """
        if not name:
            # Default profile
            return ProfilePaths(
                config=CONFIG_DIR / "embed",
                lock=CONFIG_DIR / "daemon.lock",
                log=CONFIG_DIR / "daemon.log",
                port=DEFAULT_PORT,
            )

        # Named profile - read port from .env file
        env_file = PROFILES_DIR / f"{name}.env"
        port = self._read_port_from_env(env_file)
        if port is None:
            raise ValueError(f"Profile '{name}' does not have PORT configured in {env_file}")

        return ProfilePaths(
            config=env_file,
            lock=PROFILES_DIR / f"{name}.lock",
            log=PROFILES_DIR / f"{name}.log",
            port=port,
        )

    def _read_port_from_env(self, env_file: Path) -> Optional[int]:
        """Read PORT from a profile's .env file.

        Args:
            env_file: Path to the .env file.

        Returns:
            Port number if found, None otherwise.
        """
        if not env_file.exists():
            return None

        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("PORT="):
                    return int(line.split("=", 1)[1])
        except (ValueError, IOError):
            return None

        return None

    def _check_daemon_running(self, port: int) -> bool:
        """Check if daemon is running on a port.

        Args:
            port: Port number to check.

        Returns:
            True if daemon is responding.
        """
        try:
            with httpx.Client() as client:
                response = client.get(f"http://127.0.0.1:{port}/health", timeout=1)
                return response.status_code == 200
        except Exception:
            return False


def resolve_active_profile() -> str:
    """Resolve which profile to use based on priority.

    Priority (highest to lowest):
    1. HINDSIGHT_EMBED_PROFILE environment variable
    2. CLI --profile flag (from global context)
    3. Active profile from file
    4. Default (empty string)

    Returns:
        Profile name to use (empty string for default).
    """
    # 1. Environment variable
    if env_profile := os.getenv("HINDSIGHT_EMBED_PROFILE"):
        return env_profile

    # 2. CLI flag (set by caller before invoking commands)
    from . import cli

    if cli_profile := cli.get_cli_profile_override():
        return cli_profile

    # 3. Active profile file
    pm = ProfileManager()
    if active_profile := pm.get_active_profile():
        return active_profile

    # 4. Default
    return ""


def validate_profile_exists(profile: str):
    """Validate that a profile exists, exit if not.

    Args:
        profile: Profile name to validate.

    Exits:
        If profile doesn't exist, prints error and exits.
    """
    if not profile:
        # Default profile - always valid
        return

    pm = ProfileManager()
    if not pm.profile_exists(profile):
        print(
            f"Error: Profile '{profile}' not found.",
            file=sys.stderr,
        )
        print(
            f"Create it with: hindsight-embed configure --profile {profile}",
            file=sys.stderr,
        )
        sys.exit(1)
