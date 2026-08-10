import logging
from pathlib import Path
from typing import Dict, List, Optional
from app.models import Profile, OutputFormat, MetadataPolicy, CoverPolicy
from app.services.config_manager import config_manager

logger = logging.getLogger(__name__)


class ProfileManager:
    """配置管理器 - 管理转换 Profile"""

    PROFILES_FILE = "profiles.json"

    def __init__(self):
        self.profiles: Dict[str, Profile] = {}
        self.load_profiles()

    def load_profiles(self):
        """加载配置"""
        data = config_manager.load(self.PROFILES_FILE)
        if data:
            for profile_id, profile_dict in data.items():
                self.profiles[profile_id] = Profile(**profile_dict)
        else:
            # 创建默认配置
            self._create_default_profiles()

    def _create_default_profiles(self):
        """创建默认配置"""
        defaults = [
            Profile(
                id="apple-music-aac-256",
                name="Apple Music AAC 256",
                output_format=OutputFormat.M4A,
                codec="aac",
                bitrate=256,
                sample_rate=44100,
                metadata_policy=MetadataPolicy.KEEP,
                cover_policy=CoverPolicy.EMBED,
                filename_template="{title}.{extension}",
                directory_template="{album_artist}/{year} - {album}",
            ),
            Profile(
                id="apple-lossless",
                name="Apple Lossless",
                output_format=OutputFormat.M4A,
                codec="alac",
                sample_rate=0,  # 保持源文件
                metadata_policy=MetadataPolicy.KEEP,
                cover_policy=CoverPolicy.EMBED,
                filename_template="{title}.{extension}",
                directory_template="{album_artist}/{year} - {album}",
            ),
            Profile(
                id="mp3-320",
                name="MP3 320",
                output_format=OutputFormat.MP3,
                codec="libmp3lame",
                bitrate=320,
                sample_rate=44100,
                metadata_policy=MetadataPolicy.KEEP,
                cover_policy=CoverPolicy.KEEP,
                filename_template="{title}.{extension}",
                directory_template="{album_artist}/{year} - {album}",
            ),
        ]

        for profile in defaults:
            self.profiles[profile.id] = profile

        self.save_profiles()

    def save_profiles(self):
        """保存配置"""
        data = {profile_id: profile.dict() for profile_id, profile in self.profiles.items()}
        config_manager.save(self.PROFILES_FILE, data)

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        """获取配置"""
        return self.profiles.get(profile_id)

    def get_all_profiles(self) -> List[Profile]:
        """获取所有配置"""
        return list(self.profiles.values())

    def create_profile(self, profile: Profile) -> Profile:
        """创建配置"""
        self.profiles[profile.id] = profile
        self.save_profiles()
        logger.info(f"Created profile: {profile.name}")
        return profile

    def update_profile(self, profile_id: str, profile: Profile) -> Optional[Profile]:
        """更新配置"""
        if profile_id in self.profiles:
            # 增加版本号
            profile.version = self.profiles[profile_id].version + 1
            self.profiles[profile_id] = profile
            self.save_profiles()
            logger.info(f"Updated profile: {profile.name} to version {profile.version}")
            return profile
        return None

    def delete_profile(self, profile_id: str) -> bool:
        """删除配置"""
        if profile_id in self.profiles:
            profile = self.profiles.pop(profile_id)
            self.save_profiles()
            logger.info(f"Deleted profile: {profile.name}")
            return True
        return False


profile_manager = ProfileManager()
