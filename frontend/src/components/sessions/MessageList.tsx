import { useRef, useEffect, useCallback } from 'react'
import type { Message } from '../../api/types'
import MessageBubble from './MessageBubble'
import EmptyState, { InboxIcon } from '../common/EmptyState'

interface MessageListProps {
  messages: Message[]
  isThinking?: boolean
  scrollToBottomOnMount?: boolean
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2.5 px-6 py-3 animate-[fadeSlideUp_0.2s_ease-out]">
      <div className="flex items-center gap-1">
        <span
          className="w-2 h-2 rounded-full bg-zurk-400 animate-bounce"
          style={{ animationDelay: '0ms', animationDuration: '0.8s' }}
        />
        <span
          className="w-2 h-2 rounded-full bg-zurk-400 animate-bounce"
          style={{ animationDelay: '150ms', animationDuration: '0.8s' }}
        />
        <span
          className="w-2 h-2 rounded-full bg-zurk-400 animate-bounce"
          style={{ animationDelay: '300ms', animationDuration: '0.8s' }}
        />
      </div>
      <span className="text-xs text-zurk-400 font-mono">Claude is working...</span>
    </div>
  )
}

function DateSeparator({ date }: { date: string }) {
  return (
    <div className="flex items-center gap-3 px-6 py-2">
      <div className="flex-1 h-px bg-zurk-700/50" />
      <span className="text-[10px] text-zurk-400 font-mono">{date}</span>
      <div className="flex-1 h-px bg-zurk-700/50" />
    </div>
  )
}

function formatDateLabel(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const dayMs = 86_400_000

  if (diff < dayMs && now.getDate() === date.getDate()) return 'Today'
  if (diff < 2 * dayMs) return 'Yesterday'
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function MessageList({ messages, isThinking = false, scrollToBottomOnMount = false }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const prevCountRef = useRef(messages.length)
  const seenIds = useRef(new Set<string>())
  const initialScrollDone = useRef(false)

  const isNearBottom = useCallback(() => {
    const el = containerRef.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }, [])

  // Auto-scroll on new messages (only if user is near bottom)
  useEffect(() => {
    if (messages.length > prevCountRef.current && isNearBottom()) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevCountRef.current = messages.length
  }, [messages.length, isNearBottom])

  // Scroll to bottom on initial mount (for external sessions)
  useEffect(() => {
    if (scrollToBottomOnMount && !initialScrollDone.current && messages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'instant' as ScrollBehavior })
      initialScrollDone.current = true
    }
  }, [scrollToBottomOnMount, messages.length])

  let lastDateLabel = ''

  if (messages.length === 0 && !isThinking) {
    return (
      <div className="h-full flex items-center justify-center">
        <EmptyState
          icon={<InboxIcon />}
          title="No messages yet"
          description="Send a prompt below to start the conversation with Claude."
        />
      </div>
    )
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto py-3">
      {messages.map((msg) => {
        const dateLabel = formatDateLabel(msg.timestamp)
        const showSeparator = dateLabel !== lastDateLabel
        lastDateLabel = dateLabel

        const isNew = !seenIds.current.has(msg.id)
        if (isNew) seenIds.current.add(msg.id)

        return (
          <div key={msg.id} className={isNew ? 'animate-[fadeSlideUp_0.2s_ease-out]' : undefined}>
            {showSeparator && <DateSeparator date={dateLabel} />}
            <MessageBubble message={msg} />
          </div>
        )
      })}

      {isThinking && <ThinkingIndicator />}

      <div ref={bottomRef} />
    </div>
  )
}
