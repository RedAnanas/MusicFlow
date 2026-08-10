# AGENTS.md - MusicFlow AI Agent 规范

## 项目信息

**项目名称：** MusicFlow
**项目类型：** NAS 音乐转换与整理工具
**技术栈：** Python (FastAPI) + Vue 3 + Docker
**主要功能：** 音频格式转换、元数据处理、文件监控、Web UI

---

## AI Agent 工作规范

### 1. 开始工作前

**必须执行：**
```bash
# 检查 Git 状态
git status

# 查看当前分支
git branch

# 查看最近提交
git log --oneline -10

# 确认项目结构
ls -la
```

**确认事项：**
- 工作区是否干净
- 当前分支是否正确
- 是否有未提交修改
- 是否有冲突状态

如果发现问题，**必须先询问用户**。

---

### 2. 修改范围控制

**只能修改：**
- 当前任务相关文件
- 必要的配置文件
- 必要的测试文件
- 相关文档

**禁止修改：**
- 无关代码
- 项目架构（除非任务要求）
- 依赖版本（除非必要）
- 其他模块代码

**如果需要额外修改：**
必须说明：
1. 为什么需要修改
2. 影响范围
3. 是否继续

---

### 3. 分支管理

**分支命名规范：**
```
feature/<功能名称>     # 新功能
fix/<问题名称>        # Bug 修复
refactor/<模块名称>   # 重构
docs/<内容>           # 文档修改
```

**禁止：**
- 直接在 main/master 分支修改
- 创建不规范的分支名
- 合并未完成的分支

---

### 4. Commit 规范

**格式：**
```
<type>: <description>

类型：feat | fix | docs | style | refactor | test | perf | build | ci | chore
```

**要求：**
- 每次提交只包含一个功能或修复
- 提交信息清晰描述修改内容
- 禁止混合多个无关修改

**示例：**
```
feat: add batch audio conversion
fix: resolve metadata parsing error
refactor: simplify conversion engine
```

---

### 5. 提交流程

**默认流程：**
```
AI 修改代码
    ↓
展示 git diff
    ↓
等待用户确认
    ↓
执行 commit
```

**禁止：**
- 自动执行 git commit
- 未经确认就提交
- 一次提交多个无关修改

---

### 6. 代码质量

**Python 代码：**
- 使用类型提示
- 添加必要的注释（中文）
- 完善的异常处理
- 日志记录完整
- 遵循 PEP 8

**TypeScript/Vue 代码：**
- 使用 Composition API
- 使用 TypeScript 类型
- 组件和变量命名规范
- 避免 any 类型

---

### 7. 测试要求

**提交前必须验证：**
- 代码能正常运行
- API 端点正常响应
- 前端页面正常显示
- 无语法错误

**如果有测试：**
- 运行相关测试
- 确保测试通过

---

### 8. 文档更新

**必须更新的文档：**
- 代码注释（关键部分）
- API 文档（如有变更）
- CHANGELOG.md（重要变更）
- README.md（功能变更）

---

### 9. 安全规则

**禁止提交：**
- .env 文件
- 密码、token、密钥
- 日志文件
- 数据库备份
- 临时文件

**检查方法：**
```bash
git diff --cached
# 确认没有敏感信息
```

---

### 10. 工作完成标准

**任务完成后必须输出：**

```markdown
## Summary
修改内容：xxx

## Files Changed
- 文件1
- 文件2

## Tests
- 测试情况

## Git Status
- clean / modified

## Next Steps
- 后续建议
```

---

### 11. 禁止操作

**绝对禁止：**
- git reset --hard
- git push --force
- 删除远程分支
- 修改历史提交
- 自动升级依赖
- 修改无关代码
- 跳过用户确认

---

### 12. 问题处理

**发现问题时：**
1. 立即停止工作
2. 记录问题详情
3. 询问用户如何处理
4. 等待用户指示

**不要：**
- 自行决定如何处理
- 继续执行有风险的操作
- 忽略问题继续工作

---

### 13. 沟通规范

**开始工作时：**
说明：
- 任务目标
- 计划修改的文件
- 预期结果

**工作过程中：**
- 及时更新进度
- 遇到问题立即报告
- 不确定时询问用户

**完成工作时：**
- 输出完整的工作总结
- 说明修改内容和原因
- 提供测试验证结果

---

### 14. 性能考虑

**注意：**
- 避免不必要的循环
- 优化数据库查询
- 使用异步处理
- 合理使用缓存

**不要：**
- 无理由的性能牺牲
- 复杂的实现方式
- 过度优化

---

### 15. 代码审查

**提交前自我审查：**
- 代码是否符合规范
- 是否有语法错误
- 是否有安全隐患
- 是否有性能问题
- 文档是否更新

---

## 项目结构

```
MusicFlow/
├── backend/           # 后端服务
│   ├── app/          # 应用代码
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/          # 前端服务
│   ├── src/          # 源代码
│   ├── package.json
│   └── Dockerfile
├── docs/             # 项目文档
├── CLAUDE.md         # AI 编程规范
└── AGENTS.md         # Agent 规范
```

---

## 开发环境

**启动命令：**

后端：
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload
```

前端：
```bash
cd frontend
npm install
npm run dev
```

**访问地址：**
- 前端：http://localhost:3000
- 后端：http://localhost:8082
- API 文档：http://localhost:8082/docs

---

## 联系方式

**项目维护者：** [待填写]
**问题反馈：** [待填写]
**文档位置：** /docs

---

## 版本历史

- v1.0.0 - 初始版本
- 最后更新：2026-08-10

---

**遵循这些规范，确保代码质量和项目可维护性。**
