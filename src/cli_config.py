import json
from pathlib import Path
from typing import Any


def load_run_config(path: Path, command: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as config_file:
            data = json.load(config_file)
    except OSError as error:
        raise ValueError(f"Không thể đọc file cấu hình: {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"File cấu hình không phải JSON hợp lệ: {path}: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("File cấu hình phải chứa một object JSON.")
    configured_command = data.get("command")
    if configured_command is not None and configured_command != command:
        raise ValueError(
            f"File cấu hình dành cho lệnh '{configured_command}', không phải '{command}'."
        )
    return {key: value for key, value in data.items() if key != "command"}


def config_value(
    cli_value: Any,
    values: dict[str, Any],
    name: str,
    default: Any = None,
) -> Any:
    return cli_value if cli_value is not None else values.get(name, default)
