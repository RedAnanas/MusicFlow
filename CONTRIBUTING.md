# MusicFlow 开发贡献指南

所有改动必须遵循 [AGENTS.md](AGENTS.md) 和 [开发流程](docs/development/workflow.md)。

最小交付流程：

1. 从 `develop` 创建 `feature/<name>` 或 `fix/<name>` 分支。
2. 只修改与目标直接相关的文件。
3. 为缺陷或新行为补充测试。
4. 执行 `./scripts/check.sh`。
5. 经用户允许后提交并合并到 `develop`。
6. 用户验证后，获得明确确认才能合并到 `main`。

禁止提交环境变量、账号密钥、日志、任务历史、个人音乐路径和数据库备份。
