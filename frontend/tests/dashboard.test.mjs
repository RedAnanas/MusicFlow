import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/views/Dashboard.vue', import.meta.url), 'utf8')
const declaration = source.match(/^const formatBytes = .+$/m)[0]
const formatBytes = new Function(`${ts.transpile(declaration)}; return formatBytes`)()

test('首页歌曲大小的数值与单位一致', () => {
  for (const [bytes, expected] of [
    [0, '0MB'],
    [1024 ** 2, '1MB'],
    [1024 ** 3 - 1, '1024MB'],
    [1024 ** 3, '1.00GB'],
    [1.5 * 1024 ** 3, '1.50GB'],
    [12969.32 * 1024 ** 2, '12.67GB'],
  ]) {
    assert.equal(formatBytes(bytes), expected)
  }
})
