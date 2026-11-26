import pytest


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path_factory, monkeypatch):
    """Log và file khôi phục của mọi test (kể cả app chạy trong pty) ghi vào thư mục tạm, không vào ~/.local."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path_factory.mktemp("state")))
    monkeypatch.delenv("SPLAYPAD_LOG_FILE", raising=False)
    monkeypatch.delenv("SPLAYPAD_LOG_LEVEL", raising=False)
    monkeypatch.setenv("SPLAYPAD_CLIPBOARD", "internal")       # không đụng clipboard thật của máy chạy test
