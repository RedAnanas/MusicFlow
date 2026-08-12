# AGENTS.md - MusicFlow AI Agent Rules (Codex Compatible)

## Project Info
- **Name:** MusicFlow - NAS Music Conversion Tool
- **Stack:** Python 3.12/FastAPI + Vue 3/Element Plus
- **Deploy:** Docker + Docker Compose

## Agent Behavior Rules

### 1. Think Before Coding
- State assumptions explicitly. If uncertain, ask.
- Present multiple interpretations, don't pick silently.
- Surface tradeoffs. Push back when warranted.

### 2. Simplicity First
- Minimum code that solves the problem.
- No abstractions for single-use code.
- No error handling for impossible scenarios.

### 3. Surgical Changes
- Don't modify adjacent code unless needed.
- Don't refactor things that aren't broken.
- Match existing style exactly.

### 4. Goal-Driven
- Define success criteria. Loop until verified.
- For multi-step tasks, state a plan with verification steps.

### 5. Chinese Language Priority (中文优先)
- All replies, docs, analysis in Simplified Chinese.
- Code comments in Chinese.
- Variable/function/class names in English.
- Git commits in Chinese.

## Git Workflow

### Branch Rules (CRITICAL)
```
main     - Production (NEVER commit directly)
develop  - Daily development
feature/<name> - New features from develop
fix/<name>     - Bug fixes from develop
```

### Workflow
```
1. Create branch:  git checkout -b feature/<name>
2. Develop & commit
3. Merge to develop: git checkout develop && git merge feature/<name>
4. User verifies
5. Merge to main (USER CONFIRMATION REQUIRED): git checkout main && git merge develop
```

### Commit Format
```
<type>: <description>
types: feat | fix | docs | style | refactor | test | perf | build | ci | chore
```

### Forbidden
- git reset --hard
- git push --force
- Auto-commit without permission
- Auto-merge to main

## Tech Stack
### Backend: Python 3.12+, FastAPI, Pydantic, Mutagen, FFmpeg/FFprobe, Watchdog
### Frontend: Vue 3, TypeScript, Vite, Element Plus, Pinia, Vue Router

## Project Structure
```
backend/app/ → main.py, config.py, api/routes/, core/, models/, services/, utils/
frontend/src/ → views/, stores/, router/, types/
```

## Startup
```bash
# Backend: cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8082 --reload
# Frontend: cd frontend && npm run dev
# URLs: http://localhost:3000 (frontend), http://localhost:8082 (backend/docs)
```

## Known Issues (UNFIXED)
See: `UNFIXED_ISSUES.md`
1. Profile bitrate/codec dropdowns, output format display, create function
2. Watch folder create/edit API calls
3. Metadata/cover image copy for some formats

## Security
Never commit: .env, passwords, tokens, keys, logs, database backups
