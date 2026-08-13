# 工程化开发流程

## 分支模型

```text
main                 生产主干，仅接收已验证的 develop
develop              日常集成分支
feature/<name>       新功能，从 develop 创建
fix/<name>           缺陷修复，从 develop 创建
```

禁止直接在 `main` 上开发或提交。合并到 `main` 必须获得用户明确确认。

## 开发步骤

1. 检查 `git status`，识别并保护用户已有改动。
2. 从 `develop` 创建目标明确的功能或修复分支。
3. 定义可验证的成功标准。
4. 实施最小改动，并补充对应测试。
5. 执行 `.\scripts\check.ps1`。
6. 检查差异，确保没有运行数据和无关改动。
7. 获得用户许可后提交；提交信息使用中文并符合 `<type>: <描述>`。
8. 合并至 `develop` 供用户验证。
9. 用户明确确认后才可合并并推送 `main`。

## 质量门禁

任何代码改动在提交前必须满足：

- 后端测试通过；
- Python 源码可编译；
- 前端生产构建通过；
- Docker Compose 配置有效；
- `git diff --check` 无错误；
- 未提交 `.env`、日志、任务历史、个人配置或密钥；
- 文档与实际命令、路径保持一致。

统一检查命令：

```powershell
.\scripts\check.ps1
```

## 运行数据管理

- `config/*.json`：本地 Profile、监控目录和任务数据；
- `logs/`：运行日志；
- `temp/`：临时文件与服务进程状态；
- `data/`：Docker 默认音乐卷；
- `backend/.env`：本机环境变量。

这些内容均不进入版本库。需要共享的配置必须脱敏后添加到 `config/examples/`。

## 文档管理

- 当前有效文档放在 `docs/` 对应分类中；
- 一次性过程记录和已完成问题移动到 `docs/archive/`；
- 根目录不堆放过程文档；
- `README.md` 只作为安装、运行和文档入口。
