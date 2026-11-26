"""Clipboard hệ điều hành (pbcopy/pbpaste, wl-copy/wl-paste, xclip, xsel), dùng kèm clipboard nội bộ.

``SPLAYPAD_CLIPBOARD=internal`` tắt hẳn (test, phiên SSH không có clipboard); mặc định ``auto`` dùng công cụ đầu
tiên tìm thấy. Lỗi gọi công cụ chỉ ghi log, editor quay về clipboard nội bộ.
"""

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)
TIMEOUT_S = 1.0
TOOLS = (                                                # (lệnh copy, lệnh paste)
    (["pbcopy"], ["pbpaste"]),
    (["wl-copy"], ["wl-paste", "--no-newline"]),
    (["xclip", "-selection", "clipboard"], ["xclip", "-selection", "clipboard", "-o"]),
    (["xsel", "--clipboard", "--input"], ["xsel", "--clipboard", "--output"]),
)


class SystemClipboard:
    def __init__(self, copy_cmd: list[str], paste_cmd: list[str]):
        self.copy_cmd, self.paste_cmd = copy_cmd, paste_cmd
        self.name = copy_cmd[0]

    def copy(self, data: bytes) -> bool:
        try:
            subprocess.run(self.copy_cmd, input=data, timeout=TIMEOUT_S, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("clipboard copy via %s failed: %s", self.name, e)
            return False

    def paste(self) -> bytes | None:
        try:
            r = subprocess.run(self.paste_cmd, timeout=TIMEOUT_S, check=True, capture_output=True)
            return r.stdout
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("clipboard paste via %s failed: %s", self.name, e)
            return None


def detect() -> SystemClipboard | None:
    mode = os.environ.get("SPLAYPAD_CLIPBOARD", "auto").lower()
    if mode == "internal":
        return None
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    for copy_cmd, paste_cmd in TOOLS:
        if copy_cmd[0] == "wl-copy" and not wayland:
            continue
        if copy_cmd[0] in ("xclip", "xsel") and not os.environ.get("DISPLAY"):
            continue
        if shutil.which(copy_cmd[0]) and shutil.which(paste_cmd[0]):
            log.info("system clipboard: %s", copy_cmd[0])
            return SystemClipboard(copy_cmd, paste_cmd)
    log.info("system clipboard: none (internal only)")
    return None
