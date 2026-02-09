import { useState, useMemo, useEffect } from 'react'

interface DiffViewerProps {
  diff: string
  stats?: { additions: number; deletions: number; files_changed: number }
  tier?: 'inline' | 'truncated'
  totalBytes?: number
  totalLines?: number
  defaultCollapsed?: boolean
}

// ── Diff line classification ───────────────────────────────────────

type LineKind = 'add' | 'del' | 'hunk' | 'header' | 'context' | 'omitted'

interface DiffLine {
  kind: LineKind
  text: string
  oldNum: number | null
  newNum: number | null
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/

function parseDiff(raw: string): DiffLine[] {
  const lines = raw.split('\n')
  // Remove trailing empty line (almost all diffs end with \n)
  if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop()

  const result: DiffLine[] = []
  let oldLine = 0
  let newLine = 0

  for (const text of lines) {
    // Skip "\ No newline at end of file" marker (don't count as content)
    if (text.startsWith('\\ ')) continue

    if (text.startsWith('--- ') || text.startsWith('+++ ')) {
      result.push({ kind: 'header', text, oldNum: null, newNum: null })
    } else if (text.startsWith('@@')) {
      const match = HUNK_RE.exec(text)
      if (match) {
        oldLine = parseInt(match[1], 10)
        newLine = parseInt(match[2], 10)
      }
      result.push({ kind: 'hunk', text, oldNum: null, newNum: null })
    } else if (text.startsWith('+')) {
      result.push({ kind: 'add', text, oldNum: null, newNum: newLine })
      newLine++
    } else if (text.startsWith('-')) {
      result.push({ kind: 'del', text, oldNum: oldLine, newNum: null })
      oldLine++
    } else if (text.includes('lines omitted')) {
      result.push({ kind: 'omitted', text, oldNum: null, newNum: null })
    } else {
      // Context line (starts with space or empty)
      result.push({ kind: 'context', text, oldNum: oldLine, newNum: newLine })
      oldLine++
      newLine++
    }
  }

  return result
}

// ── Styling per line kind ──────────────────────────────────────────

const kindStyles: Record<LineKind, string> = {
  add: 'bg-status-running/10 text-status-running',
  del: 'bg-status-error/10 text-status-error',
  hunk: 'bg-accent-500/5 text-accent-500',
  header: 'text-zurk-400 font-semibold',
  context: 'text-zurk-300',
  omitted: 'text-zurk-500 italic text-center',
}

// ── Component ──────────────────────────────────────────────────────

export default function DiffViewer({
  diff,
  stats,
  tier,
  totalBytes,
  totalLines,
  defaultCollapsed = false,
}: DiffViewerProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  // Sync with parent when defaultCollapsed changes (e.g., Escape key)
  useEffect(() => setCollapsed(defaultCollapsed), [defaultCollapsed])

  const lines = useMemo(() => parseDiff(diff), [diff])

  // Determine max line number width for gutter alignment
  const maxNum = useMemo(() => {
    let m = 0
    for (const l of lines) {
      if (l.oldNum !== null && l.oldNum > m) m = l.oldNum
      if (l.newNum !== null && l.newNum > m) m = l.newNum
    }
    return m
  }, [lines])
  const gutterWidth = Math.max(3, String(maxNum).length)

  return (
    <div className="rounded-lg overflow-hidden border border-zurk-600/40 bg-zurk-900">
      {/* Stats bar */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-zurk-800/50 transition-colors"
      >
        <div className="flex items-center gap-3 text-xs">
          {/* Expand/collapse chevron */}
          <svg
            className={`w-3.5 h-3.5 text-zurk-400 transition-transform ${collapsed ? '' : 'rotate-90'}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>

          {stats && (
            <>
              <span className="text-status-running font-mono">+{stats.additions}</span>
              <span className="text-status-error font-mono">-{stats.deletions}</span>
              <span className="text-zurk-500">
                {stats.files_changed} file{stats.files_changed !== 1 ? 's' : ''}
              </span>
            </>
          )}

          {tier === 'truncated' && totalBytes != null && (
            <span className="text-zurk-500">
              (truncated — {(totalBytes / 1024).toFixed(0)} KB total)
            </span>
          )}
        </div>

        {totalLines != null && (
          <span className="text-[10px] text-zurk-500">{totalLines} lines</span>
        )}
      </button>

      {/* Diff body */}
      {!collapsed && (
        <div className="overflow-x-auto max-h-80 sm:max-h-96 overflow-y-auto border-t border-zurk-700/50">
          <table className="w-full text-xs font-mono leading-5">
            <tbody>
              {lines.map((line, i) => {
                if (line.kind === 'omitted') {
                  return (
                    <tr key={i}>
                      <td colSpan={3} className={`px-3 py-1 ${kindStyles.omitted}`}>
                        {line.text}
                      </td>
                    </tr>
                  )
                }

                const showGutter = line.kind !== 'header' && line.kind !== 'hunk'

                return (
                  <tr key={i} className={kindStyles[line.kind]}>
                    {/* Old line number */}
                    <td className="select-none text-right pr-1 pl-2 text-zurk-600 w-0 whitespace-nowrap">
                      {showGutter && line.oldNum !== null
                        ? String(line.oldNum).padStart(gutterWidth, '\u00A0')
                        : '\u00A0'.repeat(gutterWidth)}
                    </td>
                    {/* New line number */}
                    <td className="select-none text-right pr-2 text-zurk-600 w-0 whitespace-nowrap border-r border-zurk-700/30">
                      {showGutter && line.newNum !== null
                        ? String(line.newNum).padStart(gutterWidth, '\u00A0')
                        : '\u00A0'.repeat(gutterWidth)}
                    </td>
                    {/* Content */}
                    <td className="px-3 whitespace-pre-wrap break-all">
                      {line.text}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
