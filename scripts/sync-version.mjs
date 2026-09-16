import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(fileURLToPath(new URL('..', import.meta.url)))
const version = readFileSync(resolve(projectRoot, 'VERSION'), 'utf8').trim()
const checkOnly = process.argv.includes('--check')

if (!/^\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$/.test(version)) {
  throw new Error(`VERSION 格式无效：${version}`)
}

const packageFiles = [
  resolve(projectRoot, 'frontend/package.json'),
  resolve(projectRoot, 'frontend/package-lock.json'),
]

let mismatched = false
for (const filename of packageFiles) {
  const content = JSON.parse(readFileSync(filename, 'utf8'))
  const currentVersion = filename.endsWith('package-lock.json')
    ? content.packages?.['']?.version
    : content.version

  if (currentVersion === version) continue
  mismatched = true
  if (checkOnly) continue

  content.version = version
  if (content.packages?.['']) content.packages[''].version = version
  writeFileSync(filename, `${JSON.stringify(content, null, 2)}\n`)
  console.log(`已同步 ${filename.replace(`${projectRoot}/`, '')}：${version}`)
}

if (checkOnly && mismatched) {
  throw new Error('前端包版本与 VERSION 不一致，请运行 node scripts/sync-version.mjs')
}

if (!mismatched) console.log(`版本一致：${version}`)
