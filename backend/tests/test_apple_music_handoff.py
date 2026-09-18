from pathlib import Path

from app.services.apple_music_handoff import AppleMusicHandoffService


def test_handoff_copies_complete_file_and_keeps_source(tmp_path: Path):
    """交接应保留转换成品，并只向自动导入目录写入完整文件。"""
    source = tmp_path / "Converted" / "测试歌曲.m4a"
    source.parent.mkdir()
    source.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"
    import_dir.mkdir()

    result = AppleMusicHandoffService().handoff(str(source), str(import_dir))

    target = Path(result)
    assert source.read_bytes() == b"music-data"
    assert target.read_bytes() == b"music-data"
    assert (import_dir / AppleMusicHandoffService.MARKER_FILE).is_file()
    assert not list(import_dir.glob("*.musicflow-copying"))


def test_handoff_rejects_unavailable_import_directory(tmp_path: Path):
    """自动导入目录不可访问时不能创建同名本地目录。"""
    source = tmp_path / "歌曲.m4a"
    source.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"

    try:
        AppleMusicHandoffService().handoff(str(source), str(import_dir))
    except FileNotFoundError as error:
        assert "自动导入目录不可访问" in str(error)
    else:
        raise AssertionError("应拒绝不可访问的自动导入目录")

    assert not import_dir.exists()


def test_handoff_rejects_local_fallback_when_network_mount_is_required(monkeypatch, tmp_path: Path):
    """容器要求 SMB 挂载时，不能向断开后的本地目录交接。"""
    source = tmp_path / "歌曲.m4a"
    source.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"
    import_dir.mkdir()
    service = AppleMusicHandoffService(require_network_mount=True)
    monkeypatch.setattr(service, "_get_mount_filesystem", lambda _path: "ext4")

    try:
        service.handoff(str(source), str(import_dir))
    except OSError as error:
        assert "SMB/CIFS 挂载不可用" in str(error)
    else:
        raise AssertionError("SMB 挂载断开时不应向本地目录交接")

    assert not (import_dir / source.name).exists()


def test_handoff_accepts_cifs_mount_when_network_mount_is_required(monkeypatch, tmp_path: Path):
    """检测到 CIFS 文件系统时应允许正常交接。"""
    source = tmp_path / "歌曲.m4a"
    source.write_bytes(b"music-data")
    import_dir = tmp_path / "Automatically Add to Apple Music"
    import_dir.mkdir()
    service = AppleMusicHandoffService(require_network_mount=True)
    monkeypatch.setattr(service, "_get_mount_filesystem", lambda _path: "cifs")

    result = service.handoff(str(source), str(import_dir))

    assert Path(result).read_bytes() == b"music-data"


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
    (tmp_path / service.MARKER_FILE).write_text("ready", encoding="utf-8")

    assert service.is_received(str(import_file)) is False
    import_file.unlink()
    assert service.is_received(str(import_file)) is True


def test_is_received_rejects_unavailable_import_directory(tmp_path: Path):
    """自动导入目录不可访问时不能判定为 Apple Music 已接收。"""
    import_file = tmp_path / "unavailable" / "歌曲.m4a"

    try:
        AppleMusicHandoffService().is_received(str(import_file))
    except FileNotFoundError as error:
        assert "自动导入目录不可访问" in str(error)
    else:
        raise AssertionError("挂载目录不可访问时不应判定为已接收")


def test_is_received_rejects_directory_without_mount_marker(tmp_path: Path):
    """挂载退回成本地空目录时不能判定为 Apple Music 已接收。"""
    import_file = tmp_path / "歌曲.m4a"

    try:
        AppleMusicHandoffService().is_received(str(import_file))
    except FileNotFoundError as error:
        assert "挂载标记不可访问" in str(error)
    else:
        raise AssertionError("缺少挂载标记时不应判定为已接收")
