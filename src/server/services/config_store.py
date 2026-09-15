"""Kho JSON duy nhất quản lý camera, baseline và cấu hình runtime."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from uuid import uuid4

from pydantic import ValidationError

from server.models.calibration import (
    CalibrationConfig,
    CalibrationCreate,
    CalibrationUpdate,
)
from server.models.camera import CameraConfig, CameraCreate, CameraUpdate
from server.models.config import AppConfigDocument, RuntimeConfig


class ConfigError(RuntimeError):
    """Báo lỗi khi tệp cấu hình không thể đọc hoặc ghi."""


class CameraNotFoundError(LookupError):
    """Báo lỗi khi không tìm thấy camera singleton theo ID."""


class CameraValidationError(ValueError):
    """Báo lỗi khi bản cập nhật camera không hợp lệ."""


class BaselineNotFoundError(LookupError):
    """Báo lỗi khi không tìm thấy baseline theo ID."""


class BaselineNameConflictError(ValueError):
    """Báo lỗi khi tên baseline đã tồn tại trong cùng một camera."""


class RuntimeValidationError(ValueError):
    """Báo lỗi khi cấu hình runtime không khớp camera hoặc baseline."""


class ConfigStore:
    """Quản lý toàn bộ cấu hình ứng dụng trong một tệp JSON nguyên tử."""

    def __init__(
        self,
        path: str | Path,
        legacy_calibration_path: str | Path | None = None,
    ):
        """Khởi tạo store và đường dẫn calibration cũ dùng khi migration."""
        self.path = Path(path)
        self.legacy_calibration_path = (
            Path(legacy_calibration_path)
            if legacy_calibration_path is not None
            else self.path.with_name("calibration.json")
        )
        self._lock = RLock()

    # ─────────────────────────────────────────────────────────────────────────

    def list_cameras(self) -> list[CameraConfig]:
        """Trả danh sách rỗng hoặc camera singleton hiện tại."""
        with self._lock:
            camera = self._read_unlocked().camera
            return [camera.model_copy(deep=True)] if camera is not None else []

    # ─────────────────────────────────────────────────────────────────────────

    def get_camera(self, camera_id: str) -> CameraConfig:
        """Lấy camera hiện tại hoặc báo lỗi khi ID không khớp."""
        with self._lock:
            camera = self._find_camera(self._read_unlocked(), camera_id)
            return camera.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def create_camera(
        self,
        payload: CameraCreate,
        camera_id: str | None = None,
    ) -> CameraConfig:
        """Lưu camera mới và ghi đè camera singleton hiện tại."""
        with self._lock:
            # Bước 1: tạo bản ghi camera mới với ID dùng chung cho MediaMTX.
            document = self._read_unlocked()
            timestamp = datetime.now(timezone.utc)
            camera = CameraConfig(
                id=camera_id or uuid4().hex[:12],
                created_at=timestamp,
                updated_at=timestamp,
                **payload.model_dump(),
            )

            # Bước 2: camera mới làm lựa chọn baseline runtime cũ mất hiệu lực.
            document.camera = camera
            document.runtime.enabled = False
            document.runtime.active_baseline_id = None
            self._write_unlocked(document)
            return camera.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def update_camera(self, camera_id: str, payload: CameraUpdate) -> CameraConfig:
        """Cập nhật camera và giữ nguyên danh sách baseline."""
        with self._lock:
            document = self._read_unlocked()
            camera = self._find_camera(document, camera_id)

            # Bước 1: ghép payload từng phần rồi validate lại bản ghi hoàn chỉnh.
            merged = camera.model_dump()
            merged.update(payload.model_dump(exclude_unset=True))
            merged["updated_at"] = datetime.now(timezone.utc)
            try:
                updated = CameraConfig.model_validate(merged)
            except ValidationError as exc:
                raise CameraValidationError(str(exc)) from exc

            # Bước 2: ghi lại document chung mà không làm mất baseline.
            document.camera = updated
            self._write_unlocked(document)
            return updated.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def delete_camera(self, camera_id: str) -> None:
        """Xóa camera nhưng giữ baseline để người dùng quản lý riêng."""
        with self._lock:
            document = self._read_unlocked()
            self._find_camera(document, camera_id)
            document.camera = None
            document.runtime.enabled = False
            document.runtime.active_baseline_id = None
            self._write_unlocked(document)

    # ─────────────────────────────────────────────────────────────────────────

    def list_baselines(self) -> list[CalibrationConfig]:
        """Trả toàn bộ baseline theo thứ tự mới nhất trước."""
        with self._lock:
            baselines = self._read_unlocked().baselines
            return [item.model_copy(deep=True) for item in reversed(baselines)]

    # ─────────────────────────────────────────────────────────────────────────

    def get_baseline(self, baseline_id: str) -> CalibrationConfig:
        """Lấy một baseline hoặc báo lỗi nếu ID không tồn tại."""
        with self._lock:
            baseline = self._find_baseline(self._read_unlocked(), baseline_id)
            return baseline.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def create_baseline(
        self,
        camera_id: str,
        payload: CalibrationCreate,
    ) -> CalibrationConfig:
        """Thêm baseline mới vào document chung."""
        with self._lock:
            # Bước 1: bảo đảm baseline liên kết với camera đang tồn tại.
            document = self._read_unlocked()
            self._find_camera(document, camera_id)
            self._ensure_unique_baseline_name(
                document,
                camera_id,
                payload.name,
            )
            timestamp = datetime.now(timezone.utc)
            baseline = CalibrationConfig(
                id=uuid4().hex[:12],
                camera_id=camera_id,
                created_at=timestamp,
                updated_at=timestamp,
                **payload.model_dump(),
            )

            # Bước 2: nối baseline mới và ghi nguyên tử toàn bộ document.
            document.baselines.append(baseline)
            self._write_unlocked(document)
            return baseline.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def update_baseline(
        self,
        baseline_id: str,
        payload: CalibrationUpdate,
    ) -> CalibrationConfig:
        """Thay thế cấu hình một baseline và giữ nguyên camera."""
        with self._lock:
            # Bước 1: dựng bản ghi mới nhưng giữ ID, camera và ngày tạo.
            document = self._read_unlocked()
            current = self._find_baseline(document, baseline_id)
            self._ensure_unique_baseline_name(
                document,
                current.camera_id,
                payload.name,
                excluded_baseline_id=current.id,
            )
            updated = CalibrationConfig(
                id=current.id,
                camera_id=current.camera_id,
                created_at=current.created_at,
                updated_at=datetime.now(timezone.utc),
                **payload.model_dump(),
            )

            # Bước 2: thay đúng vị trí trong collection rồi ghi nguyên tử.
            index = document.baselines.index(current)
            document.baselines[index] = updated
            self._write_unlocked(document)
            return updated.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def delete_baseline(self, baseline_id: str) -> None:
        """Xóa một baseline và giữ nguyên các cấu hình còn lại."""
        with self._lock:
            document = self._read_unlocked()
            baseline = self._find_baseline(document, baseline_id)
            document.baselines.remove(baseline)
            if document.runtime.active_baseline_id == baseline_id:
                document.runtime.active_baseline_id = None
                document.runtime.enabled = False
            self._write_unlocked(document)

    # ─────────────────────────────────────────────────────────────────────────

    def get_runtime(self) -> RuntimeConfig:
        """Trả bản sao cấu hình runtime hiện tại hoặc giá trị mặc định."""
        with self._lock:
            # Bước 1: không ghi file khi caller chỉ đọc cấu hình mặc định.
            return self._read_unlocked().runtime.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def update_runtime(self, runtime: RuntimeConfig) -> RuntimeConfig:
        """Validate quan hệ camera-baseline rồi lưu toàn bộ cấu hình runtime."""
        with self._lock:
            document = self._read_unlocked()
            document.runtime = runtime.model_copy(deep=True)
            try:
                # Bước 1: validate lại toàn document để kiểm tra các tham chiếu ID.
                validated = AppConfigDocument.model_validate(
                    document.model_dump(mode="python")
                )
            except ValidationError as exc:
                raise RuntimeValidationError(str(exc)) from exc

            # Bước 2: ghi nguyên tử chỉ sau khi toàn bộ schema hợp lệ.
            self._write_unlocked(validated)
            return validated.runtime.model_copy(deep=True)

    # ─────────────────────────────────────────────────────────────────────────

    def _find_camera(
        self,
        document: AppConfigDocument,
        camera_id: str,
    ) -> CameraConfig:
        """Tìm camera singleton trong document đang giữ khóa."""
        camera = document.camera
        if camera is not None and camera.id == camera_id:
            return camera
        raise CameraNotFoundError(f"Không tìm thấy camera '{camera_id}'.")

    # ─────────────────────────────────────────────────────────────────────────

    def _find_baseline(
        self,
        document: AppConfigDocument,
        baseline_id: str,
    ) -> CalibrationConfig:
        """Tìm baseline trong document đang giữ khóa."""
        for baseline in document.baselines:
            if baseline.id == baseline_id:
                return baseline
        raise BaselineNotFoundError(f"Không tìm thấy baseline '{baseline_id}'.")

    # ─────────────────────────────────────────────────────────────────────────

    def _ensure_unique_baseline_name(
        self,
        document: AppConfigDocument,
        camera_id: str,
        name: str,
        excluded_baseline_id: str | None = None,
    ) -> None:
        """Bảo đảm tên baseline không trùng trong phạm vi một camera."""
        # Bước 1: chuẩn hóa để tên chỉ khác hoa thường hoặc khoảng trắng vẫn trùng.
        normalized_name = name.strip().casefold()
        for baseline in document.baselines:
            if baseline.id == excluded_baseline_id:
                continue
            if baseline.camera_id != camera_id:
                continue
            if baseline.name.strip().casefold() == normalized_name:
                raise BaselineNameConflictError(
                    f"Tên baseline '{name.strip()}' đã tồn tại cho camera này."
                )

    # ─────────────────────────────────────────────────────────────────────────

    def _read_unlocked(self) -> AppConfigDocument:
        """Đọc config chung và nhập calibration cũ khi chưa hợp nhất."""
        # Bước 1: đọc config chính hoặc tạo document rỗng.
        config_exists = self.path.exists()
        if not config_exists:
            document = AppConfigDocument()
            is_unified = False
        else:
            payload = self._read_json(self.path)
            is_unified = isinstance(payload, dict) and "baselines" in payload
            try:
                document = AppConfigDocument.model_validate(payload)
            except ValidationError as exc:
                raise ConfigError(
                    f"Cấu hình không hợp lệ tại '{self.path}': {exc}"
                ) from exc

        # Bước 2: chỉ nhập calibration.json khi config chưa từng dùng schema chung.
        imported_legacy = False
        if not is_unified and self.legacy_calibration_path.exists():
            legacy_payload = self._read_json(self.legacy_calibration_path)
            try:
                legacy_document = AppConfigDocument.model_validate(legacy_payload)
            except ValidationError as exc:
                raise ConfigError(
                    "Cấu hình calibration cũ không hợp lệ tại "
                    f"'{self.legacy_calibration_path}': {exc}"
                ) from exc
            known_ids = {item.id for item in document.baselines}
            imported_baselines = [
                item
                for item in legacy_document.baselines
                if item.id not in known_ids
            ]
            document.baselines.extend(imported_baselines)
            imported_legacy = bool(imported_baselines)

        # Bước 3: ghi schema chung một lần sau khi đọc dữ liệu legacy thành công.
        if (config_exists and not is_unified) or imported_legacy:
            self._write_unlocked(document)
        return document

    # ─────────────────────────────────────────────────────────────────────────

    def _read_json(self, path: Path) -> object:
        """Đọc một tệp JSON và chuẩn hóa lỗi hệ thống."""
        try:
            with path.open("r", encoding="utf-8") as stream:
                return json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Không thể đọc cấu hình tại '{path}': {exc}") from exc

    # ─────────────────────────────────────────────────────────────────────────

    def _write_unlocked(self, document: AppConfigDocument) -> None:
        """Ghi document chung qua tệp tạm rồi thay thế nguyên tử."""
        # Bước 1: tạo thư mục và tệp tạm trên cùng filesystem với config chính.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(
                    document.model_dump(mode="json"),
                    stream,
                    ensure_ascii=False,
                    indent=2,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())

            # Bước 2: bảo vệ URL camera rồi thay thế config trong một thao tác.
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise ConfigError(
                f"Không thể ghi cấu hình tại '{self.path}': {exc}"
            ) from exc
