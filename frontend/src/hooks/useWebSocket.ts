import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { connectWebSocket, connectSSE } from '../api/client'
import type { StreamMessage } from '../api/types'

// ── Configuration ───────────────────────────────────────────────────

const MAX_WS_FAILURES = 3
const RECONNECT_BASE_MS = 1_000
const RECONNECT_MAX_MS = 30_000
const PING_INTERVAL_MS = 25_000
const PONG_TIMEOUT_MS = 10_000

// ── Types ───────────────────────────────────────────────────────────

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'fallback-sse' | 'disconnected'
type Transport = 'websocket' | 'sse'

interface UseWebSocketOptions {
  sessionId: string
  enabled?: boolean
  onMessage?: (msg: StreamMessage) => void
}

interface UseWebSocketReturn {
  connectionState: ConnectionState
  transport: Transport | null
  send: (data: Record<string, unknown>) => void
  disconnect: () => void
}

// ── Hook ────────────────────────────────────────────────────────────

export function useWebSocket({
  sessionId,
  enabled = true,
  onMessage,
}: UseWebSocketOptions): UseWebSocketReturn {
  const queryClient = useQueryClient()
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [transport, setTransport] = useState<Transport | null>(null)

  // Refs for mutable state that shouldn't trigger re-renders
  const wsRef = useRef<WebSocket | null>(null)
  const sseRef = useRef<EventSource | null>(null)
  const onMessageRef = useRef(onMessage)
  const wsFailures = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pingTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const pongTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const intentionalClose = useRef(false)

  onMessageRef.current = onMessage

  // ── Helpers ─────────────────────────────────────────────────────

  const handleStreamMessage = useCallback((msg: StreamMessage) => {
    onMessageRef.current?.(msg)

    // Invalidate React Query caches based on message type
    switch (msg.type) {
      case 'status':
      case 'result':
      case 'approval_required':
      case 'approval_processed':
        queryClient.invalidateQueries({ queryKey: ['session', sessionId] })
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        break
    }
  }, [sessionId, queryClient])

  const clearTimers = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    if (pingTimer.current) clearInterval(pingTimer.current)
    if (pongTimer.current) clearTimeout(pongTimer.current)
  }, [])

  const closeAll = useCallback(() => {
    intentionalClose.current = true
    clearTimers()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (sseRef.current) {
      sseRef.current.close()
      sseRef.current = null
    }
    setTransport(null)
    setConnectionState('disconnected')
  }, [clearTimers])

  // ── WebSocket ping/pong keepalive ───────────────────────────────

  const startPing = useCallback(() => {
    if (pingTimer.current) clearInterval(pingTimer.current)

    pingTimer.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ command: 'ping' }))

        // If no pong within timeout, reconnect
        pongTimer.current = setTimeout(() => {
          if (wsRef.current) {
            wsRef.current.close()
          }
        }, PONG_TIMEOUT_MS)
      }
    }, PING_INTERVAL_MS)
  }, [])

  // ── SSE fallback ────────────────────────────────────────────────

  const connectWithSSE = useCallback(() => {
    if (sseRef.current) sseRef.current.close()

    setConnectionState('fallback-sse')
    setTransport('sse')

    const source = connectSSE(sessionId, handleStreamMessage)

    source.onopen = () => {
      setConnectionState('connected')
    }

    source.onerror = () => {
      // SSE auto-reconnects by default, just update state
      setConnectionState('reconnecting')
    }

    sseRef.current = source
  }, [sessionId, handleStreamMessage])

  // ── WebSocket connection with reconnection ──────────────────────

  const connectWithWS = useCallback(() => {
    if (wsRef.current) wsRef.current.close()
    intentionalClose.current = false

    setConnectionState('connecting')
    setTransport('websocket')

    const ws = connectWebSocket(sessionId, {
      onOpen: () => {
        setConnectionState('connected')
        wsFailures.current = 0
        startPing()
      },

      onMessage: (msg) => {
        // Clear pong timeout if we get any message (pong or otherwise)
        if (pongTimer.current) clearTimeout(pongTimer.current)
        handleStreamMessage(msg)
      },

      onClose: () => {
        clearTimers()
        if (intentionalClose.current) return

        wsFailures.current += 1

        if (wsFailures.current >= MAX_WS_FAILURES) {
          // Fall back to SSE
          connectWithSSE()
          return
        }

        // Exponential backoff reconnect
        const delay = Math.min(
          RECONNECT_BASE_MS * Math.pow(2, wsFailures.current - 1),
          RECONNECT_MAX_MS,
        )
        setConnectionState('reconnecting')
        reconnectTimer.current = setTimeout(connectWithWS, delay)
      },

      onError: () => {
        // onClose will fire after onError, reconnection is handled there
      },
    })

    wsRef.current = ws
  }, [sessionId, handleStreamMessage, startPing, clearTimers, connectWithSSE])

  // ── Effect: connect / disconnect on sessionId or enabled change ─

  useEffect(() => {
    if (!enabled || !sessionId) {
      closeAll()
      return
    }

    wsFailures.current = 0
    connectWithWS()

    return () => {
      closeAll()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, enabled])

  // ── Public API ──────────────────────────────────────────────────

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return {
    connectionState,
    transport,
    send,
    disconnect: closeAll,
  }
}
