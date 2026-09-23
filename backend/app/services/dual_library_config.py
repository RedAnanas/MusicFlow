from app.services.config_manager import config_manager


class DualLibraryConfigService:
    """分别保存本地音乐库与 Apple Music 补齐使用的监控目录。"""

    FILE_NAME = "dual_library.json"

    def get(self) -> dict[str, str]:
        saved = config_manager.load(self.FILE_NAME) or {}
        return {
            "nas_watch_folder_id": str(saved.get("nas_watch_folder_id") or ""),
            "apple_watch_folder_id": str(saved.get("apple_watch_folder_id") or ""),
            "apple_storefront": str(saved.get("apple_storefront") or "cn").lower(),
            "legacy_watch_folder_id": str(saved.get("watch_folder_id") or ""),
        }

    def resolve(self) -> dict[str, str]:
        """兼容旧单目录配置，并按目录实际输出能力迁移到对应目标。"""
        values = self.get()
        legacy_id = values.pop("legacy_watch_folder_id")
        if not legacy_id or values["nas_watch_folder_id"] or values["apple_watch_folder_id"]:
            return values

        from app.models import DeliveryTargetType
        from app.services.profile_manager import profile_manager
        from app.services.watch_folder_manager import watch_folder_manager

        folder = watch_folder_manager.get_watch_folder(legacy_id)
        if not folder:
            return values
        if any(target.type == DeliveryTargetType.COPY for target in folder.targets):
            values["nas_watch_folder_id"] = legacy_id
        if any(
            target.type == DeliveryTargetType.CONVERT
            and (profile := profile_manager.get_profile(target.profile_id or "")) is not None
            and profile.apple_music_handoff_enabled
            and bool(profile.apple_music_import_dir)
            for target in folder.targets
        ):
            values["apple_watch_folder_id"] = legacy_id
        return values

    def save(
        self,
        nas_watch_folder_id: str,
        apple_watch_folder_id: str,
        apple_storefront: str = "cn",
    ) -> dict[str, str]:
        values = {
            "nas_watch_folder_id": nas_watch_folder_id.strip(),
            "apple_watch_folder_id": apple_watch_folder_id.strip(),
            "apple_storefront": apple_storefront.strip().lower() or "cn",
        }
        if not config_manager.save(self.FILE_NAME, values):
            raise OSError("保存双库监控目录配置失败")
        return values


dual_library_config = DualLibraryConfigService()
