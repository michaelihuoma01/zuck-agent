import { useState, type ReactNode } from 'react'
import type { Message } from '../../api/types'

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-3.5 h-3.5 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
      onClick={handleCopy}
      className="text-[10px] text-zurk-500 hover:text-zurk-300 transition-colors px-1.5 py-0.5 rounded"
      title="Copy to clipboard"
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function tryFormatJSON(text: string): string {
  try {
    const parsed = JSON.parse(text)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return text
  }
}

// ── Tool Use ────────────────────────────────────────────────────────

/** Color the tool name based on its category */
function toolNameColor(name: string): string {
  switch (name) {
    case 'Read': case 'Glob': case 'Grep':
      return 'text-syntax-blue'
    case 'Write': case 'Edit': case 'NotebookEdit':
      return 'text-syntax-yellow'
    case 'Bash':
      return 'text-syntax-orange'
    case 'WebSearch': case 'WebFetch':
      return 'text-syntax-purple'
    case 'Task':
      return 'text-syntax-cyan'
    default:
      return 'text-zurk-300'
  }
}

/** Is the tool preview a file path? Color it blue */
function isPathPreview(toolName: string): boolean {
  return ['Read', 'Write', 'Edit', 'Glob', 'Grep'].includes(toolName)
}

function ToolUseMessage({ message }: { message: Message }) {
  const [expanded, setExpanded] = useState(false)
  const toolName = (message.metadata?.tool_name as string) ?? 'unknown'
  const toolInput = message.metadata?.tool_input as Record<string, unknown> | undefined

  const body = toolInput
    ? JSON.stringify(toolInput, null, 2)
    : tryFormatJSON(message.content)

  const previewLine = getToolPreview(toolName, toolInput, message.content)

  return (
    <div className="mx-4 sm:mx-5 my-1.5">
      <div className="bg-zurk-800/40 rounded-xl overflow-hidden transition-colors hover:bg-zurk-800/60">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2 px-3 py-2 text-left transition-colors"
        >
          <ChevronIcon open={expanded} />
          <span className="text-[10px] font-mono text-zurk-500 uppercase tracking-[0.2em]">Tool</span>
          <span className={`text-xs font-semibold font-mono ${toolNameColor(toolName)}`}>{toolName}</span>
          {!expanded && previewLine && (
            <span className={`text-xs truncate ml-1 flex-1 font-mono ${
              isPathPreview(toolName) ? 'text-syntax-blue/70' : 'text-zurk-500'
            }`}>
              {previewLine}
            </span>
          )}
          <span className="text-[10px] text-zurk-600 shrink-0 ml-auto">
            {formatTime(message.timestamp)}
          </span>
        </button>

        {expanded && (
          <div className="border-t border-zurk-700/30 relative">
            <div className="absolute top-1 right-1">
              <CopyButton text={body} />
            </div>
            <pre className="text-xs text-zurk-300 font-mono whitespace-pre-wrap break-all p-3 max-h-80 overflow-y-auto">
              {body}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tool Result ─────────────────────────────────────────────────────

function ToolResultMessage({ message }: { message: Message }) {
  const [expanded, setExpanded] = useState(false)
  const isError = message.metadata?.is_error as boolean | undefined

  const lines = message.content.split('\n')
  const isLong = lines.length > 4 || message.content.length > 300

  return (
    <div className="mx-4 sm:mx-5 my-1">
      <div
        className={`rounded-xl overflow-hidden ${
          isError
            ? 'bg-syntax-red/5 border border-syntax-red/10'
            : 'bg-zurk-800/30'
        }`}
      >
        <button
          onClick={() => isLong && setExpanded(!expanded)}
          className={`w-full flex items-center gap-2 px-3 py-1.5 text-left ${
            isLong ? 'hover:bg-zurk-800/40 cursor-pointer' : 'cursor-default'
          } transition-colors`}
        >
          {isLong && <ChevronIcon open={expanded} />}
          {isError && (
            <svg className="w-3 h-3 text-syntax-red shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
            </svg>
          )}
          <span className={`text-[10px] uppercase tracking-[0.2em] ${isError ? 'text-syntax-red' : 'text-zurk-500'}`}>
            {isError ? 'Error' : 'Result'}
          </span>
          {isLong && !expanded && (
            <span className={`text-xs truncate flex-1 ${isError ? 'text-syntax-red/70' : 'text-zurk-500'}`}>
              {lines[0]?.slice(0, 80)}
            </span>
          )}
          <CopyButton text={message.content} />
        </button>

        {(!isLong || expanded) && (
          <div className={`border-t ${isError ? 'border-syntax-red/10' : 'border-zurk-700/30'}`}>
            <pre className={`text-xs font-mono whitespace-pre-wrap break-all p-3 max-h-80 overflow-y-auto ${
              isError ? 'text-syntax-red/90' : 'text-zurk-300'
            }`}>
              {message.content}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────

function getToolPreview(
  toolName: string,
  toolInput: Record<string, unknown> | undefined,
  content: string,
): string {
  if (!toolInput) return content.slice(0, 60)

  switch (toolName) {
    case 'Read':
      return String(toolInput.file_path ?? '')
    case 'Write':
    case 'Edit':
      return String(toolInput.file_path ?? '')
    case 'Bash':
      return String(toolInput.command ?? '').slice(0, 80)
    case 'Glob':
      return String(toolInput.pattern ?? '')
    case 'Grep':
      return String(toolInput.pattern ?? '')
    case 'WebSearch':
      return String(toolInput.query ?? '')
    case 'WebFetch':
      return String(toolInput.url ?? '')
    default:
      return Object.values(toolInput)
        .filter((v) => typeof v === 'string')
        .join(', ')
        .slice(0, 80)
  }
}

// ── Rich text renderer ──────────────────────────────────────────────
//
// Handles: code blocks, headings, blockquotes, horizontal rules, lists,
// bold, italic, inline code, file paths, URLs, error/warning keywords.

const CODE_BLOCK_RE = /```(\w*)\n([\s\S]*?)```/g
const INLINE_CODE_RE = /`([^`\n]+)`/g
const BOLD_RE = /\*\*(.+?)\*\*/g
const ITALIC_RE = /(?<!\*)\*([^*\n]+)\*(?!\*)/g
const FILE_PATH_RE = /(?:^|\s)((?:\/|\.\.?\/)[^\s,;:!?)]+\.[a-zA-Z0-9]{1,10})/g
const URL_RE = /(https?:\/\/[^\s)<>]+)/g
const HEADING_RE = /^(#{1,3})\s+(.+)$/
const BLOCKQUOTE_RE = /^>\s?(.*)$/
const HR_RE = /^[-*_]{3,}$/
const ERROR_KEYWORDS = /\b(error|Error|ERROR|failed|Failed|FAILED|exception|Exception|EXCEPTION|panic|PANIC|fatal|FATAL|TypeError|ReferenceError|SyntaxError|RuntimeError|ValueError|KeyError|ImportError|ModuleNotFoundError|FileNotFoundError|PermissionError|ConnectionError|TimeoutError|AttributeError)\b/g
const WARNING_KEYWORDS = /\b(warning|Warning|WARNING|warn|WARN|deprecated|DEPRECATED|caution|CAUTION)\b/g
const SUCCESS_KEYWORDS = /\b(success|Success|SUCCESS|passed|PASSED|✓|✅|completed|COMPLETED)\b/g

function renderRichText(text: string): ReactNode[] {
  const elements: ReactNode[] = []
  let key = 0

  // Split on code blocks first (they're opaque — nothing inside is processed)
  const parts = text.split(CODE_BLOCK_RE)
  // parts: [before, lang1, code1, between, lang2, code2, ...]

  for (let i = 0; i < parts.length; i++) {
    if (i % 3 === 1) continue // language token
    if (i % 3 === 2) {
      const lang = parts[i - 1] || ''
      elements.push(
        <div key={key++} className="my-2 rounded-lg overflow-hidden border border-zurk-700/40">
          {lang && (
            <div className="bg-zurk-800 px-3 py-1 text-[10px] text-zurk-500 font-mono uppercase tracking-wider border-b border-zurk-700/40">
              {lang}
            </div>
          )}
          <pre className="bg-zurk-950 text-zurk-200 text-xs font-mono px-3 py-2.5 overflow-x-auto">
            {parts[i]}
          </pre>
        </div>,
      )
      continue
    }

    // Process line-level block elements, then group into paragraphs
    const lines = parts[i].split('\n')
    let paragraphBuffer: string[] = []

    const flushParagraph = () => {
      if (paragraphBuffer.length === 0) return
      const joined = paragraphBuffer.join('\n')
      paragraphBuffer = []
      if (!joined.trim()) return

      // Check if the buffer is a list
      const bufLines = joined.split('\n')
      const isList = bufLines.every(
        (l) => !l.trim() || /^(\d+\.\s|[-*]\s)/.test(l.trim()),
      )

      if (isList) {
        const items = bufLines.filter((l) => l.trim())
        const isOrdered = /^\d+\./.test(items[0]?.trim() ?? '')
        const Tag = isOrdered ? 'ol' : 'ul'
        elements.push(
          <Tag
            key={key++}
            className={`text-sm my-1.5 space-y-0.5 pl-4 ${isOrdered ? 'list-decimal' : 'list-disc'} text-zurk-200`}
          >
            {items.map((item, li) => (
              <li key={li} className="leading-relaxed">
                {renderInline(item.replace(/^\s*(\d+\.\s|[-*]\s)/, ''))}
              </li>
            ))}
          </Tag>,
        )
      } else {
        elements.push(
          <p key={key++} className="text-sm leading-relaxed text-zurk-200 my-1">
            {renderInline(joined)}
          </p>,
        )
      }
    }

    // Blockquote accumulator
    let blockquoteBuffer: string[] = []

    const flushBlockquote = () => {
      if (blockquoteBuffer.length === 0) return
      const content = blockquoteBuffer.join('\n')
      blockquoteBuffer = []
      elements.push(
        <blockquote
          key={key++}
          className="border-l-2 border-syntax-purple/60 pl-3 my-2 text-sm text-zurk-300 italic"
        >
          {renderInline(content)}
        </blockquote>,
      )
    }

    for (const line of lines) {
      const trimmed = line.trim()

      // Empty line → flush current paragraph
      if (!trimmed) {
        flushBlockquote()
        flushParagraph()
        continue
      }

      // Horizontal rule
      if (HR_RE.test(trimmed)) {
        flushBlockquote()
        flushParagraph()
        elements.push(
          <hr key={key++} className="border-zurk-700/50 my-3" />,
        )
        continue
      }

      // Heading
      const headingMatch = trimmed.match(HEADING_RE)
      if (headingMatch) {
        flushBlockquote()
        flushParagraph()
        const level = headingMatch[1].length
        const cls = level === 1
          ? 'text-base font-semibold text-zurk-50 mt-4 mb-1'
          : level === 2
            ? 'text-sm font-semibold text-zurk-100 mt-3 mb-1'
            : 'text-sm font-medium text-zurk-200 mt-2 mb-0.5'
        elements.push(
          <p key={key++} className={cls}>
            {renderInline(headingMatch[2])}
          </p>,
        )
        continue
      }

      // Blockquote
      const bqMatch = trimmed.match(BLOCKQUOTE_RE)
      if (bqMatch) {
        flushParagraph()
        blockquoteBuffer.push(bqMatch[1])
        continue
      }

      // Regular line → accumulate into paragraph
      flushBlockquote()
      paragraphBuffer.push(line)
    }

    flushBlockquote()
    flushParagraph()
  }

  return elements
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let key = 0

  // Split on inline code first (opaque — nothing processed inside)
  const codeParts = text.split(INLINE_CODE_RE)
  for (let i = 0; i < codeParts.length; i++) {
    if (i % 2 === 1) {
      nodes.push(
        <code key={key++} className="bg-zurk-800 text-syntax-cyan text-[13px] font-mono px-1 py-0.5 rounded">
          {codeParts[i]}
        </code>,
      )
    } else {
      nodes.push(...renderPlainText(codeParts[i], key))
      key += countSegments(codeParts[i])
    }
  }

  return nodes
}

/** Process bold → italic → URLs → file paths → error/warning/success keywords */
function renderPlainText(text: string, startKey: number): ReactNode[] {
  const nodes: ReactNode[] = []
  let key = startKey

  // Split on bold
  const boldParts = text.split(BOLD_RE)
  for (let j = 0; j < boldParts.length; j++) {
    if (j % 2 === 1) {
      nodes.push(
        <strong key={key++} className="font-semibold text-zurk-50">{boldParts[j]}</strong>,
      )
    } else {
      // Split on italic
      const italicParts = boldParts[j].split(ITALIC_RE)
      for (let k = 0; k < italicParts.length; k++) {
        if (k % 2 === 1) {
          nodes.push(
            <em key={key++} className="italic text-zurk-300">{italicParts[k]}</em>,
          )
        } else {
          nodes.push(...renderTokens(italicParts[k], key))
          key += countTokenSegments(italicParts[k])
        }
      }
    }
  }

  return nodes
}

/** Final pass: URLs, file paths, error/warning/success keywords */
function renderTokens(text: string, startKey: number): ReactNode[] {
  if (!text) return []
  const nodes: ReactNode[] = []
  let key = startKey

  // Combined regex for all token types (order matters: URLs before file paths)
  const TOKEN_RE = new RegExp(
    `(${URL_RE.source})|${FILE_PATH_RE.source}|${ERROR_KEYWORDS.source}|${WARNING_KEYWORDS.source}|${SUCCESS_KEYWORDS.source}`,
    'g',
  )

  let lastIndex = 0
  let match: RegExpExecArray | null
  TOKEN_RE.lastIndex = 0

  while ((match = TOKEN_RE.exec(text)) !== null) {
    const before = text.slice(lastIndex, match.index)
    if (before) nodes.push(<span key={key++}>{before}</span>)

    const matched = match[0]

    // URL
    if (match[1]) {
      nodes.push(
        <a
          key={key++}
          href={matched}
          target="_blank"
          rel="noopener noreferrer"
          className="text-syntax-blue underline decoration-syntax-blue/30 hover:decoration-syntax-blue/70 transition-colors"
        >
          {matched}
        </a>,
      )
    }
    // File path (match[2] is the captured group from FILE_PATH_RE)
    else if (match[2]) {
      // Preserve the leading whitespace that was part of the match
      const leading = matched.slice(0, matched.length - match[2].length)
      if (leading) nodes.push(<span key={key++}>{leading}</span>)
      nodes.push(
        <span key={key++} className="text-syntax-blue font-mono text-[13px]">{match[2]}</span>,
      )
    }
    // Error keywords
    else if (ERROR_KEYWORDS.test(matched)) {
      nodes.push(
        <span key={key++} className="text-syntax-red font-medium">{matched}</span>,
      )
      ERROR_KEYWORDS.lastIndex = 0
    }
    // Warning keywords
    else if (WARNING_KEYWORDS.test(matched)) {
      nodes.push(
        <span key={key++} className="text-syntax-yellow">{matched}</span>,
      )
      WARNING_KEYWORDS.lastIndex = 0
    }
    // Success keywords
    else if (SUCCESS_KEYWORDS.test(matched)) {
      nodes.push(
        <span key={key++} className="text-syntax-green">{matched}</span>,
      )
      SUCCESS_KEYWORDS.lastIndex = 0
    }
    else {
      nodes.push(<span key={key++}>{matched}</span>)
    }

    lastIndex = match.index + matched.length
  }

  const rest = text.slice(lastIndex)
  if (rest) nodes.push(<span key={key++}>{rest}</span>)

  return nodes
}

// Key counting helpers (so parent callers can track unique keys)
function countSegments(text: string): number {
  return (text.match(BOLD_RE) || []).length * 2 + text.length + 50
}
function countTokenSegments(text: string): number {
  return text.length + 50
}

// ── Main component ──────────────────────────────────────────────────

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  const isToolUse = message.message_type === 'tool_use'
  const isToolResult = message.message_type === 'tool_result'

  if (isSystem) {
    return (
      <div className="flex items-center gap-2 px-4 sm:px-5 py-1.5">
        <div className="h-px flex-1 bg-zurk-700/40" />
        <span className="text-[10px] text-zurk-500 font-mono shrink-0 uppercase tracking-wider">
          {message.content}
        </span>
        <div className="h-px flex-1 bg-zurk-700/40" />
      </div>
    )
  }

  if (isToolUse) return <ToolUseMessage message={message} />
  if (isToolResult) return <ToolResultMessage message={message} />

  // ── Terminal-style text rendering ───────────────────────────────

  if (isUser) {
    return (
      <div className="px-4 sm:px-5 py-2 border-l-2 border-syntax-cyan/40 bg-syntax-cyan/[0.03]">
        <div className="flex items-start gap-2">
          <span className="text-syntax-cyan font-mono text-sm mt-0.5 shrink-0 select-none">&gt;</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-zurk-100 whitespace-pre-wrap break-words leading-relaxed">
              {message.content}
            </p>
          </div>
          <span className="text-[10px] text-zurk-600 shrink-0 mt-0.5">{formatTime(message.timestamp)}</span>
        </div>
      </div>
    )
  }

  // Assistant message — rich text
  return (
    <div className="px-4 sm:px-5 py-2 border-l-2 border-syntax-purple/30 bg-syntax-purple/[0.02]">
      <div className="min-w-0">
        {renderRichText(message.content)}
      </div>
      <p className="text-[10px] mt-1 text-zurk-600">{formatTime(message.timestamp)}</p>
    </div>
  )
}
