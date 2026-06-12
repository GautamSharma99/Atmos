import abc
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log, RetryCallState

# Initialize logger
logger = structlog.get_logger(__name__)


def log_retry_attempt(retry_state: RetryCallState) -> None:
    """Logs details when a retry attempt is triggered."""
    fn_name = retry_state.fn.__name__ if retry_state.fn else "fetch"
    logger.warning(
        "Ingestion request failed, retrying...",
        attempt=retry_state.attempt_number,
        next_action_delay=retry_state.idle_for,
        function=fn_name,
        error=str(retry_state.outcome.exception()) if retry_state.outcome and retry_state.outcome.failed else None
    )


class BaseCollector(abc.ABC):
    """
    Abstract Base Class for ingestion collectors.
    Provides standard async HTTP clients, structured logging, and resilient retries.
    """

    def __init__(self, name: str, timeout_seconds: float = 10.0):
        self.name = name
        self.logger = logger.bind(collector=name)
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": f"Atmos-AirQualityCast-{name}/1.0"}
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=log_retry_attempt,
        reraise=True
    )
    async def fetch_get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None
    ) -> httpx.Response:
        """
        Executes a GET request asynchronously with built-in tenacity retries.
        """
        self.logger.debug("Executing GET request", url=url, params=params)
        response = await self.client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=log_retry_attempt,
        reraise=True
    )
    async def fetch_post(
        self,
        url: str,
        json_data: dict | None = None,
        headers: dict[str, str] | None = None
    ) -> httpx.Response:
        """
        Executes a POST request asynchronously with built-in tenacity retries.
        """
        self.logger.debug("Executing POST request", url=url)
        response = await self.client.post(url, headers=headers, json=json_data)
        response.raise_for_status()
        return response

    @abc.abstractmethod
    async def collect(self) -> None:
        """
        Ingestion logic to be implemented by specific collectors.
        """
        pass

    async def close(self) -> None:
        """
        Properly clean up the client resources.
        """
        await self.client.aclose()
        self.logger.debug("HTTP client session closed")
