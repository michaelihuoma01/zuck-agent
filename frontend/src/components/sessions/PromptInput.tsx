import { useState, useRef, useCallback } from 'react'

interface PromptInputProps {
  onSend: (prompt: string) => void
  disabled?: boolean
  loading?: boolean
  placeholder?: string
}

const MAX_CHARS = 10_000

export default function PromptInput({
  onSend,
  disabled = false,
  loading = false,
  placeholder = 'Send a message...',
}: PromptInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim()
    if (!trimmed || disabled || loading) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [value, disabled, loading, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const isCmdEnter = e.key === 'Enter' && (e.metaKey || e.ctrlKey)
    const isPlainEnter = e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey

    if (isCmdEnter || isPlainEnter) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 180)}px`
    }
  }

  const charCount = value.length
  const isOverLimit = charCount > MAX_CHARS

  return (
    <div className="border-t border-zurk-700/70 bg-zurk-900/95 backdrop-blur-md px-5 sm:px-6 pt-3 pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
      <div className="flex items-end gap-3">
        <div className="flex-1 relative">
          <span className="absolute left-3 top-2.5 text-zurk-500 font-mono text-sm">$</span>
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-zurk-800/60 border border-zurk-700/50 rounded-xl pl-8 pr-4 py-2.5
              text-sm text-zurk-100 placeholder:text-zurk-600 font-mono
              focus:outline-none focus:ring-2 focus:ring-white/10 focus:border-zurk-500
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all"
          />
        </div>
        <button
          onClick={handleSubmit}
          disabled={disabled || loading || !value.trim() || isOverLimit}
          className="shrink-0 w-10 h-10 flex items-center justify-center rounded-xl
            bg-zurk-700 text-zurk-200 hover:bg-zurk-600 hover:text-white
            disabled:opacity-20 disabled:cursor-not-allowed
            transition-all active:scale-95"
          title="Send (Enter or Cmd+Enter)"
        >
          {loading ? (
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          )}
        </button>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-2 px-1">
        <p className="text-[10px] text-zurk-500">
          Enter to send · Shift+Enter for new line
        </p>
        {charCount > 0 && (
          <p className={`text-[10px] tabular-nums ${isOverLimit ? 'text-status-error' : 'text-zurk-500'}`}>
            {charCount.toLocaleString()}{isOverLimit && ` / ${MAX_CHARS.toLocaleString()}`}
          </p>
        )}
      </div>
    </div>
  )
}
