from visualisation.viewer import view
from radar.replay import synthetic_samples


def test_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLBACKEND", "Agg")
    path = tmp_path / "frame.png"
    view(synthetic_samples(3), save=path)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
