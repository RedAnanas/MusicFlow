import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

router = APIRouter()


class OutputFormat(str, Enum):
    M4A = "m4a"
    MP3 = "mp3"
    FLAC = "flac"
    ALAC = "alac"
    WAV = "wav"
    OGG = "ogg"
    OPUS = "opus"


class MetadataPolicy(str, Enum):
    KEEP = "keep"
    OVERWRITE = "overwrite"
    STRIP = "strip"


class CoverPolicy(str, Enum):
    KEEP = "keep"
    EMBED = "embed"
    KEEP_AND_EMBED = "keep_and_embed"
    STRIP = "strip"


class ProfileCreate(BaseModel):
    name: str
    enabled: bool = True
    output_format: OutputFormat
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bit_depth: Optional[int] = None
    metadata_policy: MetadataPolicy = MetadataPolicy.KEEP
    cover_policy: CoverPolicy = CoverPolicy.EMBED
    filename_template: str = "{title}.{extension}"
    directory_template: str = "{album_artist}/{year} - {album}"
    output_dir: Optional[str] = None


class ProfileUpdate(BaseModel):
    """部分更新 Profile 的模型"""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    output_format: Optional[OutputFormat] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bit_depth: Optional[int] = None
    metadata_policy: Optional[MetadataPolicy] = None
    cover_policy: Optional[CoverPolicy] = None
    filename_template: Optional[str] = None
    directory_template: Optional[str] = None
    output_dir: Optional[str] = None


class ProfileResponse(BaseModel):
    """Profile 响应模型 - 不包含版本字段"""
    id: str
    name: str
    enabled: bool
    output_format: OutputFormat
    codec: Optional[str]
    bitrate: Optional[int]
    sample_rate: Optional[int]
    channels: Optional[int]
    bit_depth: Optional[int]
    metadata_policy: MetadataPolicy
    cover_policy: CoverPolicy
    filename_template: str
    directory_template: str
    output_dir: Optional[str]


@router.get("/", response_model=List[ProfileResponse])
async def get_profiles():
    """获取所有配置"""
    from app.services.profile_manager import profile_manager
    profiles = profile_manager.get_all_profiles()
    result = []
    for p in profiles:
        profile_dict = p.dict()
        # 移除版本字段
        profile_dict.pop('version', None)
        result.append(ProfileResponse(**profile_dict))
    return result


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str):
    """获取单个配置"""
    from app.services.profile_manager import profile_manager
    profile = profile_manager.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile_dict = profile.dict()
    profile_dict.pop('version', None)
    return ProfileResponse(**profile_dict)


@router.post("/", response_model=ProfileResponse)
async def create_profile(profile_create: ProfileCreate):
    """创建配置"""
    from app.services.profile_manager import profile_manager
    from app.models import Profile, OutputFormat as ModelOutputFormat

    try:
        profile = Profile(
            id=str(uuid.uuid4()),
            name=profile_create.name,
            enabled=profile_create.enabled,
            output_format=ModelOutputFormat(profile_create.output_format.value),
            codec=profile_create.codec,
            bitrate=profile_create.bitrate,
            sample_rate=profile_create.sample_rate,
            channels=profile_create.channels,
            bit_depth=profile_create.bit_depth,
            metadata_policy=profile_create.metadata_policy.value,
            cover_policy=profile_create.cover_policy.value,
            filename_template=profile_create.filename_template,
            directory_template=profile_create.directory_template,
            output_dir=profile_create.output_dir,
        )

        created_profile = profile_manager.create_profile(profile)
        profile_dict = created_profile.dict()
        profile_dict.pop('version', None)
        return ProfileResponse(**profile_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}")


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: str, profile_update: ProfileUpdate):
    """更新配置 - 支持部分更新"""
    from app.services.profile_manager import profile_manager
    from app.models import Profile, OutputFormat as ModelOutputFormat

    # 获取现有配置
    existing_profile = profile_manager.get_profile(profile_id)
    if not existing_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    try:
        # 合并更新数据
        update_data = profile_update.model_dump(exclude_unset=True)

        # 构建更新后的 Profile
        profile_dict = existing_profile.dict()
        profile_dict.update(update_data)

        # 转换枚举值
        if 'output_format' in update_data and update_data['output_format']:
            profile_dict['output_format'] = ModelOutputFormat(update_data['output_format'].value)
        else:
            profile_dict['output_format'] = ModelOutputFormat(profile_dict['output_format'].value)

        if 'metadata_policy' in update_data and update_data['metadata_policy']:
            profile_dict['metadata_policy'] = update_data['metadata_policy'].value
        elif isinstance(profile_dict['metadata_policy'], str):
            pass  # 保持字符串

        if 'cover_policy' in update_data and update_data['cover_policy']:
            profile_dict['cover_policy'] = update_data['cover_policy'].value
        elif isinstance(profile_dict['cover_policy'], str):
            pass  # 保持字符串

        # 移除版本字段
        profile_dict.pop('version', None)

        profile = Profile(**profile_dict)

        updated_profile = profile_manager.update_profile(profile_id, profile)
        if not updated_profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        result_dict = updated_profile.dict()
        result_dict.pop('version', None)
        return ProfileResponse(**result_dict)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str):
    """删除配置"""
    from app.services.profile_manager import profile_manager
    success = profile_manager.delete_profile(profile_id)
    if not success:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success", "message": f"Profile {profile_id} deleted"}
