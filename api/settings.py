"""Local server settings; intentionally independent of model/API-key configuration."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_port: int = 8000
    api_port: int = 8001
    verification_enabled: bool = False
    data_dir: Path | None = None

    def __post_init__(self):
        if not all(1024 <= port <= 65535 for port in (self.app_port, self.api_port)):
            raise ValueError("Cổng phải nằm trong khoảng 1024–65535.")
        if self.app_port == self.api_port:
            raise ValueError("App và API phải dùng hai cổng khác nhau.")

    @property
    def origins(self):
        return [f"http://{host}:{self.app_port}" for host in ("127.0.0.1", "localhost")]

    @property
    def api_hosts(self):
        return {f"{host}:{self.api_port}" for host in ("127.0.0.1", "localhost")}

    @property
    def trusted_origins(self):
        # Swagger on the API origin is also a first-party browser client.
        return self.origins + [f"http://{host}:{self.api_port}" for host in ("127.0.0.1", "localhost")]
