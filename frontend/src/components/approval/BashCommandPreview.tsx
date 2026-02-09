interface BashCommandPreviewProps {
  command: string
  description?: string
  workingDirectory?: string
  riskLevel?: 'high' | 'medium' | 'low'
}

// ── Risk styling ───────────────────────────────────────────────────

const riskConfig = {
  high: {
    icon: '⚠',
    label: 'Dangerous',
    badge: 'bg-status-error/20 text-status-error',
    border: 'border-status-error/30',
  },
  medium: {
    icon: '⚡',
    label: 'Caution',
    badge: 'bg-status-waiting/20 text-status-waiting',
    border: 'border-status-waiting/30',
  },
  low: {
    icon: '$',
    label: '',
    badge: '',
    border: 'border-zurk-600/40',
  },
}

// ── Command hinting ────────────────────────────────────────────────

const commandHints: [RegExp, string][] = [
  [/\brm\s+-rf\b/, 'Recursively force-delete files'],
  [/\brm\b/, 'Delete files'],
  [/\bgit\s+push\s+--force\b/, 'Force-push to remote (overwrites history)'],
  [/\bgit\s+push\b/, 'Push commits to remote'],
  [/\bgit\s+reset\s+--hard\b/, 'Discard all local changes'],
  [/\bgit\s+checkout\b/, 'Switch branch or restore files'],
  [/\bpip\s+install\b/, 'Install Python package'],
  [/\bnpm\s+install\b/, 'Install Node.js package'],
  [/\bcurl\b.*\|\s*(sh|bash)\b/, 'Download and execute remote script'],
  [/\bsudo\b/, 'Run with elevated privileges'],
  [/\bmkdir\b/, 'Create directory'],
  [/\bcp\b/, 'Copy files'],
  [/\bmv\b/, 'Move/rename files'],
  [/\bchmod\b/, 'Change file permissions'],
  [/\bdocker\b/, 'Docker container operation'],
  [/\bpytest\b/, 'Run Python tests'],
  [/\bnpm\s+run\b/, 'Run npm script'],
  [/\bnpx\b/, 'Execute npm package binary'],
]

function getCommandHint(command: string): string | null {
  for (const [pattern, hint] of commandHints) {
    if (pattern.test(command)) return hint
  }
  return null
}

// ── Syntax highlighting for bash ───────────────────────────────────

function highlightCommand(command: string): React.ReactNode {
  // Split compound commands by operators but keep operators visible
  const parts = command.split(/(\s*(?:&&|\|\||;)\s*)/)

  return (
    <span>
      {parts.map((part, i) => {
        const trimmed = part.trim()
        if (trimmed === '&&' || trimmed === '||' || trimmed === ';') {
          return (
            <span key={i} className="text-zurk-500">{part}</span>
          )
        }

        // First token is the command name
        const tokens = part.match(/^(\s*)(\S+)(.*)/)
        if (!tokens) return <span key={i}>{part}</span>

        return (
          <span key={i}>
            {tokens[1]}
            <span className="text-accent-500 font-semibold">{tokens[2]}</span>
            <span className="text-zurk-200">{tokens[3]}</span>
          </span>
        )
      })}
    </span>
  )
}

// ── Component ──────────────────────────────────────────────────────

export default function BashCommandPreview({
  command,
  description,
  workingDirectory,
  riskLevel = 'low',
}: BashCommandPreviewProps) {
  const risk = riskConfig[riskLevel]
  const hint = description ?? getCommandHint(command)

  return (
    <div className={`rounded-lg overflow-hidden border bg-zurk-900 ${risk.border}`}>
      {/* Header with risk badge */}
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="text-xs font-mono text-zurk-400">Bash</span>
        {riskLevel !== 'low' && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${risk.badge}`}>
            {risk.icon} {risk.label}
          </span>
        )}
        {workingDirectory && (
          <span className="text-[10px] text-zurk-500 ml-auto font-mono truncate max-w-[50%]">
            {workingDirectory}
          </span>
        )}
      </div>

      {/* Command */}
      <div className="border-t border-zurk-700/50 px-3 py-3">
        <pre className="text-sm font-mono whitespace-pre-wrap break-all leading-relaxed">
          <span className="text-zurk-500 select-none">$ </span>
          {highlightCommand(command)}
        </pre>
      </div>

      {/* Hint */}
      {hint && (
        <div className="border-t border-zurk-700/30 px-3 py-2">
          <p className="text-[11px] text-zurk-400">{hint}</p>
        </div>
      )}
    </div>
  )
}
