import fs from 'node:fs'
import path from 'node:path'
import ts from 'typescript'

// Native controls belong in primitives. Public marketing and low-level select
// internals have different semantics and are deliberately outside this rule.
const root = path.resolve(import.meta.dirname, '../src')
const exceptions = new Set(['components/ui/Controls.tsx', 'components/BaseSelect.tsx'])
const failures = []
const totals = {}
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name)
    if (entry.isDirectory()) { if (entry.name !== '__tests__') walk(file); continue }
    if (!file.endsWith('.tsx')) continue
    const relative = path.relative(root, file)
    if (relative.startsWith('features/landing/') || exceptions.has(relative)) continue
    const source = fs.readFileSync(file, 'utf8')
    const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    function visit(node) {
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const tag = node.tagName.getText(tree)
        const attrs = node.attributes.getText(tree)
        const nativeField = tag === 'input' && !/type=["'](?:checkbox|radio|hidden|file|range|color|image|button|submit|reset)/.test(attrs)
        if (/^(PopoverButton|ListboxButton|MenuButton|DisclosureButton|ComboboxButton)$/.test(tag) && !attrs.includes('data-db-control')) failures.push(`${relative}:${tree.getLineAndCharacterOfPosition(node.pos).line + 1}: headless trigger needs shared data-db-control geometry`)
        if (tag === 'button' || nativeField) failures.push(`${relative}:${tree.getLineAndCharacterOfPosition(node.pos).line + 1}: use ControlButton or ControlInput`)
        if (tag === 'ControlButton' || tag === 'ControlInput') totals[tag] = (totals[tag] ?? 0) + 1
      }
      ts.forEachChild(node, visit)
    }
    visit(tree)
  }
}
walk(root)
// Toolbar aliases must resolve to the shared token. A second stylesheet once
// restored 44px wrappers around 34px controls and escaped component-only checks.
function checkStyles(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name)
    if (entry.isDirectory()) { checkStyles(file); continue }
    if (!file.endsWith('.css')) continue
    const source = fs.readFileSync(file, 'utf8')
    for (const match of source.matchAll(/(--[\w-]+control-height)\s*:\s*([^;}]+)/g)) {
      if (!match[2].trim().startsWith('var(--control-height)')) failures.push(`${path.relative(root, file)}: ${match[1]} must use var(--control-height)`)
    }
  }
}
checkStyles(root)
if (failures.length) { console.error(failures.join('\n')); process.exitCode = 1 }
else console.log('Shared controls check passed:', totals)
