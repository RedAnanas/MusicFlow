from pathlib import Path

from app.services.apple_music_handoff import AppleMusicHandoffService


def test_handoff_copies_complete_file_and_keeps_source(tmp_path: Path):
    """交接应保留转换成品，并只向自动导入目录写入完整文件。"""
    source = tmp_path / "Converted" / "测试歌曲.m4a"
    source.parent.mkdir()
    source.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"

    result = AppleMusicHandoffService().handoff(str(source), str(import_dir))

    target = Path(result)
    assert source.read_bytes() == b"music-data"
    assert target.read_bytes() == b"music-data"
    assert not list(import_dir.glob("*.musicflow-copying"))


def test_handoff_reuses_same_size_pending_file(tmp_path: Path):
    """重试时存在相同大小的待接收文件不应重复复制。"""
    source = tmp_path / "歌曲.m4a"
    source.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"
    import_dir.mkdir()
    target = import_dir / source.name
    target.write_bytes(b"other-data")

    result = AppleMusicHandoffService().handoff(str(source), str(import_dir))

    assert result == str(target)
    assert target.read_bytes() == b"other-data"


def test_is_received_when_apple_music_moves_import_file(tmp_path: Path):
    """自动导入文件被 Apple Music 移走后，应判定为已接收。"""
    import_file = tmp_path / "歌曲.m4a"
    import_file.write_bytes(b"music-data")
    service = AppleMusicHandoffService()

    assert service.is_received(str(import_file)) is False
    import_file.unlink()
    assert service.is_received(str(import_file)) is True
