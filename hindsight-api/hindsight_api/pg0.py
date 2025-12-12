import asyncio
import logging
from typing import Optional

from pg0 import Pg0

logger = logging.getLogger(__name__)

# pg0 configuration
DEFAULT_PORT = 5555
DEFAULT_USERNAME = "hindsight"
DEFAULT_PASSWORD = "hindsight"
DEFAULT_DATABASE = "hindsight"


class EmbeddedPostgres:
    """
    Manages an embedded PostgreSQL server instance using pg0-embedded.

    This class handles:
    - Starting/stopping the PostgreSQL server
    - Getting the connection URI

    Example:
        pg = EmbeddedPostgres()
        await pg.start()
        uri = await pg.get_uri()
        # ... use uri with asyncpg ...
        await pg.stop()
    """

    def __init__(
        self,
        version: str = "latest",
        port: int = DEFAULT_PORT,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
        database: str = DEFAULT_DATABASE,
        name: str = "hindsight",
    ):
        """
        Initialize the embedded PostgreSQL manager.

        Args:
            version: Version of PostgreSQL (not used, kept for API compatibility)
            port: Port to listen on. Defaults to 5555
            username: Username for the database. Defaults to "hindsight"
            password: Password for the database. Defaults to "hindsight"
            database: Database name to create. Defaults to "hindsight"
            name: Instance name for pg0. Defaults to "hindsight"
        """
        self.version = version
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.name = name

        self._pg0: Optional[Pg0] = None

    def _get_pg0(self) -> Pg0:
        """Get or create the Pg0 instance."""
        if self._pg0 is None:
            self._pg0 = Pg0(
                name=self.name,
                port=self.port,
                username=self.username,
                password=self.password,
                database=self.database,
            )
        return self._pg0

    def is_installed(self) -> bool:
        """Check if pg0-embedded is available. Always returns True since it's a Python package."""
        return True

    async def ensure_installed(self) -> None:
        """Ensure pg0-embedded is available. No-op since it's installed as a Python package."""
        pass

    async def start(self, max_retries: int = 3, retry_delay: float = 2.0) -> str:
        """
        Start the PostgreSQL server with retry logic.

        Args:
            max_retries: Maximum number of start attempts (default: 3)
            retry_delay: Initial delay between retries in seconds (default: 2.0)

        Returns:
            The connection URI for the started server.

        Raises:
            RuntimeError: If the server fails to start after all retries.
        """
        logger.info(
            f"Starting embedded PostgreSQL (name: {self.name}, port: {self.port})..."
        )

        pg0 = self._get_pg0()
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, pg0.start)
                uri = info.uri
                logger.info(f"PostgreSQL started on port {self.port}")
                return uri
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))
                    logger.debug(
                        f"pg0 start attempt {attempt}/{max_retries} failed: {last_error}"
                    )
                    logger.debug(f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.debug(
                        f"pg0 start attempt {attempt}/{max_retries} failed: {last_error}"
                    )

        raise RuntimeError(
            f"Failed to start embedded PostgreSQL after {max_retries} attempts. "
            f"Last error: {last_error}"
        )

    async def stop(self) -> None:
        """Stop the PostgreSQL server."""
        pg0 = self._get_pg0()
        logger.info(f"Stopping embedded PostgreSQL (name: {self.name})...")

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, pg0.stop)
            logger.info("Embedded PostgreSQL stopped")
        except Exception as e:
            error_msg = str(e).lower()
            if "not running" in error_msg:
                return
            raise RuntimeError(f"Failed to stop PostgreSQL: {e}")

    async def get_uri(self) -> str:
        """Get the connection URI for the PostgreSQL server."""
        pg0 = self._get_pg0()
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, pg0.info)
        if info is None or not info.running:
            raise RuntimeError("PostgreSQL server is not running or URI not available")
        return info.uri

    async def status(self) -> dict:
        """Get the status of the PostgreSQL server."""
        try:
            pg0 = self._get_pg0()
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, pg0.info)
            if info is None:
                return {"installed": True, "running": False}
            return {
                "installed": True,
                "running": info.running,
                "uri": info.uri if info.running else None,
            }
        except Exception:
            return {"installed": True, "running": False}

    async def is_running(self) -> bool:
        """Check if the PostgreSQL server is currently running."""
        try:
            pg0 = self._get_pg0()
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, pg0.info)
            return info is not None and info.running
        except Exception:
            return False

    async def ensure_running(self) -> str:
        """
        Ensure the PostgreSQL server is running.

        Starts if not running.

        Returns:
            The connection URI.
        """
        if await self.is_running():
            return await self.get_uri()

        return await self.start()

    def uninstall(self) -> None:
        """No-op. pg0-embedded is managed via pip."""
        pass

    def clear_data(self) -> None:
        """Remove all PostgreSQL data (destructive!)."""
        try:
            pg0 = self._get_pg0()
            pg0.drop()
            logger.info(f"Dropped pg0 instance {self.name}")
        except Exception as e:
            logger.warning(f"Failed to drop pg0 instance {self.name}: {e}")


# Convenience functions

_default_instance: Optional[EmbeddedPostgres] = None


def get_embedded_postgres() -> EmbeddedPostgres:
    """Get or create the default EmbeddedPostgres instance."""
    global _default_instance

    if _default_instance is None:
        _default_instance = EmbeddedPostgres()

    return _default_instance


async def start_embedded_postgres() -> str:
    """
    Quick start function for embedded PostgreSQL.

    Starts PostgreSQL in one call.

    Returns:
        Connection URI string

    Example:
        db_url = await start_embedded_postgres()
        conn = await asyncpg.connect(db_url)
    """
    pg = get_embedded_postgres()
    return await pg.ensure_running()


async def stop_embedded_postgres() -> None:
    """Stop the default embedded PostgreSQL instance."""
    global _default_instance

    if _default_instance:
        await _default_instance.stop()
