"""OpenServer adapter for COM connection management.

Provides live execution of OpenServer commands via the Windows COM interface.
Handles license checking, connection lifecycle, and error handling.

License Optimization:
- Tracks which PETEX applications are currently open (PROSPER, MBAL, GAP)
- Ensures only 1 PROSPER instance and 1 MBAL instance are active at any time
- GAP can remain open as the orchestrator while PROSPER/MBAL cycle
- Provides start_app/shutdown_app methods for explicit lifecycle control
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from petex_mcp.models.commands import OpenServerCommand

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of executing a single OpenServer command."""

    command: OpenServerCommand
    success: bool
    value: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of executing a batch of OpenServer commands."""

    success: bool
    results: list[CommandResult] = field(default_factory=list)
    error: Optional[str] = None
    license_available: bool = True


class LicenseManager:
    """Tracks active PETEX application instances for license optimization.

    Ensures:
    - Max 1 PROSPER instance at a time
    - Max 1 MBAL instance at a time
    - GAP can stay open as orchestrator
    - Applications are shut down before opening a new model in the same app
    """

    def __init__(self) -> None:
        self._active_apps: dict[str, bool] = {
            "PROSPER": False,
            "MBAL": False,
            "GAP": False,
        }
        self._active_models: dict[str, Optional[str]] = {
            "PROSPER": None,
            "MBAL": None,
            "GAP": None,
        }

    @property
    def active_apps(self) -> dict[str, bool]:
        return self._active_apps.copy()

    @property
    def active_models(self) -> dict[str, Optional[str]]:
        return self._active_models.copy()

    def is_active(self, app: str) -> bool:
        return self._active_apps.get(app.upper(), False)

    def mark_started(self, app: str, model_path: Optional[str] = None) -> None:
        app_upper = app.upper()
        self._active_apps[app_upper] = True
        if model_path:
            self._active_models[app_upper] = model_path

    def mark_shutdown(self, app: str) -> None:
        app_upper = app.upper()
        self._active_apps[app_upper] = False
        self._active_models[app_upper] = None

    def can_start(self, app: str) -> bool:
        app_upper = app.upper()
        if app_upper == "GAP":
            return True
        return not self._active_apps.get(app_upper, False)

    def needs_shutdown_before(self, app: str) -> bool:
        return self.is_active(app)

    def get_commands_to_free_license(self, app: str) -> list[OpenServerCommand]:
        app_upper = app.upper()
        if not self.is_active(app_upper):
            return []
        commands = []
        current_model = self._active_models.get(app_upper)
        if current_model:
            commands.append(
                OpenServerCommand(
                    method="DoCmd",
                    target=f'{app_upper}.SAVEFILE("{current_model}")',
                )
            )
        commands.append(
            OpenServerCommand(method="DoCmd", target=f"{app_upper}.SHUTDOWN()")
        )
        return commands

    def reset(self) -> None:
        for app in self._active_apps:
            self._active_apps[app] = False
            self._active_models[app] = None


class OpenServerAdapter:
    """Adapter for PETEX applications via OpenServer COM.

    Includes LicenseManager to ensure only 1 PROSPER and 1 MBAL active at a time.
    """

    def __init__(self) -> None:
        self._connection = None
        self._connected = False
        self.license_manager = LicenseManager()

    def check_license(self) -> bool:
        try:
            import win32com.client
            server = win32com.client.Dispatch("PX32.OpenServer.1")
            self._connection = server
            self._connected = True
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _ensure_connection(self) -> bool:
        if self._connected and self._connection is not None:
            return True
        return self.check_license()

    def start_app(self, app: str, model_path: Optional[str] = None) -> ExecutionResult:
        """Start app respecting license limits. Shuts down existing instance first."""
        if not self._ensure_connection():
            return ExecutionResult(success=False, error="No COM connection", license_available=False)

        commands: list[OpenServerCommand] = []
        if self.license_manager.needs_shutdown_before(app):
            commands.extend(self.license_manager.get_commands_to_free_license(app))

        commands.append(OpenServerCommand(method="DoCmd", target=f'{app.upper()}.START("")'))
        if model_path:
            commands.append(
                OpenServerCommand(method="DoCmd", target=f'{app.upper()}.OPENFILE("{model_path}")')
            )

        result = self.execute_commands(commands)
        if result.success:
            self.license_manager.mark_started(app, model_path)
        return result

    def shutdown_app(self, app: str, save_model: Optional[str] = None) -> ExecutionResult:
        """Shutdown app, freeing its license slot."""
        if not self._ensure_connection():
            return ExecutionResult(success=False, error="No COM connection")

        commands: list[OpenServerCommand] = []
        if save_model:
            commands.append(
                OpenServerCommand(method="DoCmd", target=f'{app.upper()}.SAVEFILE("{save_model}")')
            )
        commands.append(OpenServerCommand(method="DoCmd", target=f"{app.upper()}.SHUTDOWN()"))

        result = self.execute_commands(commands)
        self.license_manager.mark_shutdown(app)
        return result

    def execute_commands(self, commands: list[OpenServerCommand]) -> ExecutionResult:
        if not self._ensure_connection():
            return ExecutionResult(success=False, error="No PETEX license", license_available=False)

        results: list[CommandResult] = []
        server = self._connection

        for cmd in commands:
            try:
                cmd_result = self._execute_single(server, cmd)
                results.append(cmd_result)
            except Exception as e:
                results.append(CommandResult(command=cmd, success=False, error=str(e)))

        all_success = all(r.success for r in results)
        return ExecutionResult(success=all_success, results=results)

    async def execute(self, commands: list[OpenServerCommand]) -> list[CommandResult]:
        import asyncio
        loop = asyncio.get_event_loop()
        exec_result = await loop.run_in_executor(None, self.execute_commands, commands)
        return exec_result.results

    def _execute_single(self, server, cmd: OpenServerCommand) -> CommandResult:
        method = cmd.method
        target = cmd.target
        value = cmd.value

        try:
            if method == "DoSet":
                server.SetValue(target, str(value) if value is not None else "")
                return CommandResult(command=cmd, success=True)
            elif method == "DoGet":
                result_value = server.GetValue(target)
                return CommandResult(command=cmd, success=True, value=str(result_value))
            elif method in ("DoCmd", "DoSlowCmd", "DoGAPFunc"):
                server.DoCommand(target)
                return CommandResult(command=cmd, success=True)
            else:
                server.DoCommand(target)
                return CommandResult(command=cmd, success=True)
        except Exception as e:
            return CommandResult(command=cmd, success=False, error=str(e))

    def shutdown(self, app: str = "PROSPER") -> None:
        if self._connected and self._connection:
            try:
                self._connection.DoCommand(f"{app}.SHUTDOWN()")
                self.license_manager.mark_shutdown(app)
            except Exception:
                pass

    def disconnect(self) -> None:
        self._connection = None
        self._connected = False
        self.license_manager.reset()


_adapter_instance: Optional[OpenServerAdapter] = None


def get_adapter() -> OpenServerAdapter:
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = OpenServerAdapter()
    return _adapter_instance
