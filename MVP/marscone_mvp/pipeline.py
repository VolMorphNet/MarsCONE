"""Pipeline execution helpers for running MarsCONE modules from MVP."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from marscone_mvp.config_templates import build_all_configs


MODULE_DIRS = {
    "generator": "generator-py",
    "finder": "finder-py",
    "analyzer": "analyzer-py",
}


class PipelineRunner(QObject):
    """Run selected MarsCONE modules in an isolated runtime workspace."""

    log_emitted = Signal(str)
    status_changed = Signal(str)
    module_started = Signal(str)
    module_finished = Signal(str, bool)
    pipeline_finished = Signal(bool)

    def __init__(self, mvp_root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.mvp_root = mvp_root
        self.runtime_root = self.mvp_root / ".runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.process: QProcess | None = None
        self.pending_modules: list[str] = []
        self.current_module: str | None = None
        self.current_state: dict | None = None

    def is_running(self) -> bool:
        """Return True when a module process is currently active."""
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def run_modules(self, modules: list[str], state: dict) -> None:
        """Start a module queue using the current UI state snapshot."""
        if self.is_running():
            self.log_emitted.emit("A process is already running.")
            return

        self.pending_modules = modules[:]
        self.current_state = state
        self._start_next_module()

    def stop(self) -> None:
        """Stop the currently running module process, if any."""
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.status_changed.emit("Process stopped by user.")

    def _start_next_module(self) -> None:
        """Prepare and run the next module from the pending queue."""
        if not self.pending_modules:
            self.current_module = None
            self.pipeline_finished.emit(True)
            self.status_changed.emit("Pipeline finished.")
            return

        assert self.current_state is not None
        module_name = self.pending_modules.pop(0)
        self.current_module = module_name
        self.module_started.emit(module_name)
        self.status_changed.emit(f"Preparing {module_name}...")

        module_dir = self._prepare_runtime_module(module_name, self.current_state)
        python_executable = self.current_state.get("python_executable") or "python"

        self.process = QProcess(self)
        self.process.setProgram(python_executable)
        self.process.setArguments(["main.py"])
        self.process.setWorkingDirectory(str(module_dir))
        process_environment = QProcessEnvironment.systemEnvironment()
        if self.current_state["crs"].get("ignore_celestial_body", False):
            process_environment.insert("PROJ_IGNORE_CELESTIAL_BODY", "YES")
        self.process.setProcessEnvironment(process_environment)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

        self.log_emitted.emit(f"\n=== Running {module_name} ===")
        self.log_emitted.emit(f"Working directory: {module_dir}")
        self.process.start()
        self.status_changed.emit(f"Running {module_name}...")

    def _prepare_runtime_module(self, module_name: str, state: dict) -> Path:
        dev_root = Path(state["dev_root"])
        source_dir = dev_root / MODULE_DIRS[module_name]
        session_name = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        session_root = self.runtime_root / session_name
        session_root.mkdir(parents=True, exist_ok=True)

        target_dir = session_root / MODULE_DIRS[module_name]
        shutil.copytree(
            source_dir,
            target_dir,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".pytest_cache",
                ".ruff_cache",
                ".mypy_cache",
            ),
        )

        configs = build_all_configs(state)
        config_path = target_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(configs[module_name], handle, indent=2)

        if module_name == "analyzer":
            self._patch_analyzer_runtime(target_dir / "main.py")

        return target_dir

    def _patch_analyzer_runtime(self, main_file: Path) -> None:
        text = main_file.read_text(encoding="utf-8")

        if "def safe_degrees(value):" not in text:
            needle = "def to_point_geometry(geometry):\n"
            helper = (
                "def safe_degrees(value):\n"
                "    \"\"\"Convert radians to degrees, preserving None values.\"\"\"\n"
                "    if value is None:\n"
                "        return None\n"
                "    return float(np.degrees(value))\n\n\n"
                "def to_point_geometry(geometry):\n"
            )
            text = text.replace(needle, helper, 1)

        text = text.replace(
            '"base_angle_deg": np.degrees(theta_b),',
            '"base_angle_deg": safe_degrees(theta_b),',
        )
        text = text.replace(
            '"top_angle_deg": np.degrees(theta_t),',
            '"top_angle_deg": safe_degrees(theta_t),',
        )

        main_file.write_text(text, encoding="utf-8")

    def _read_process_buffer(self, reader) -> str:
        if self.process is None:
            return ""
        data = reader()
        return bytes(data).decode("utf-8", errors="replace")

    def _on_stdout(self) -> None:
        if self.process is None:
            return
        text = self._read_process_buffer(self.process.readAllStandardOutput)
        if text:
            self.log_emitted.emit(text.rstrip())

    def _on_stderr(self) -> None:
        if self.process is None:
            return
        text = self._read_process_buffer(self.process.readAllStandardError)
        if text:
            self.log_emitted.emit(text.rstrip())

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        module_name = self.current_module or "unknown"
        success = exit_status == QProcess.NormalExit and exit_code == 0
        self.module_finished.emit(module_name, success)

        if success:
            self.status_changed.emit(f"{module_name} finished successfully.")
            self._start_next_module()
            return

        self.status_changed.emit(f"{module_name} failed.")
        self.pipeline_finished.emit(False)
