"""从本地媒体中读取歌词并原样提取嵌入封面。"""

from pathlib import Path
import subprocess


def extract_media_extras(source, info, ffmpeg, output_dir):
    """返回歌词与封面描述；调用者负责保护输出目录和处理上传。"""
    tags = info.get("format", {}).get("tags", {})
    lyrics = next((value for key, value in tags.items()
                   if key.casefold() == "lyrics" and isinstance(value, str) and value.strip()), None)
    result = {"lyrics": lyrics, "cover": None}
    cover = next((stream for stream in info.get("streams", [])
                  if stream.get("disposition", {}).get("attached_pic") == 1), None)
    if cover is None:
        return result
    formats = {"mjpeg": ("jpg", "jpeg", "image/jpeg"), "png": ("png", "png", "image/png")}
    if cover.get("codec_name") not in formats:
        raise ValueError("嵌入封面仅支持 JPEG 或 PNG")
    extension, image_format, content_type = formats[cover["codec_name"]]
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("embedded-cover." + extension)
    try:
        completed = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-map", "0:" + str(cover["index"]), "-c:v", "copy", "-frames:v", "1", str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        raise RuntimeError("无法运行封面提取程序") from None
    if completed.returncode or not path.is_file() or not path.stat().st_size:
        path.unlink(missing_ok=True)
        raise RuntimeError("嵌入封面提取失败")
    result["cover"] = {"path": path, "format": image_format, "content_type": content_type,
                       "size": path.stat().st_size}
    return result
