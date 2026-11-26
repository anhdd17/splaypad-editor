"""Logging của ứng dụng (docs/decisions.md, ADR-014).

curses chiếm cả màn hình nên log chỉ ghi ra file, xoay vòng theo kích thước. Vị trí mặc định theo XDG:
``$XDG_STATE_HOME/splaypad/splaypad.log`` (thường là ``~/.local/state/splaypad/splaypad.log``).

Không ghi nội dung văn bản hay chuỗi người dùng gõ/tìm – chỉ sự kiện, kích thước, thời gian, lỗi.

Thứ tự ưu tiên cấu hình: tham số dòng lệnh > biến môi trường ``SPLAYPAD_LOG_LEVEL`` / ``SPLAYPAD_LOG_FILE``
> mặc định (INFO, đường dẫn XDG). Mức ``OFF`` tắt hẳn log.
"""

import logging
import logging.handlers
import os
from pathlib import Path

ROOT = "splaypad"
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "OFF")
FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(process)d] %(name)s: %(message)s"
DATEFMT = "%Y-%m-%dT%H:%M:%S"
MAX_BYTES = 1 << 20         # 1MB mỗi file
BACKUPS = 3                 # giữ splaypad.log.1 … .3


def default_path() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "splaypad" / "splaypad.log"


def setup(level: str | None = None, path: str | os.PathLike | None = None) -> Path | None:
    """Cấu hình logger ``splaypad``; trả về file log đang dùng, hoặc None nếu log bị tắt / không ghi được.

    Không bao giờ ném ngoại lệ: không ghi được log thì editor vẫn phải chạy.
    """
    level = (level or os.environ.get("SPLAYPAD_LOG_LEVEL") or "INFO").upper()
    if level not in LEVELS:
        level = "INFO"
    logger = logging.getLogger(ROOT)
    logger.propagate = False                            # không lọt ra root logger (stderr) khi curses đang vẽ
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    if level == "OFF":
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL + 1)
        return None
    file = Path(path or os.environ.get("SPLAYPAD_LOG_FILE") or default_path()).expanduser()
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(file, maxBytes=MAX_BYTES, backupCount=BACKUPS,
                                                       encoding="utf-8")
    except OSError:
        logger.addHandler(logging.NullHandler())
        return None
    handler.setFormatter(logging.Formatter(FORMAT, DATEFMT))
    logger.addHandler(handler)
    logger.setLevel(level)
    return file
