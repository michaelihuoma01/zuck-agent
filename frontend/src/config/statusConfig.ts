import type { SessionStatus } from '../api/types'

export interface StatusVariant {
  label: string
  color: string
  dotColor: string
  bgColor: string
}

export const STATUS_CONFIG: Record<SessionStatus, StatusVariant> = {
  idle: {
    label: 'Active',
    color: 'text-status-running',
    dotColor: 'bg-status-running',
    bgColor: 'bg-status-running/10',
  },
  running: {
    label: 'Running',
    color: 'text-status-running',
    dotColor: 'bg-status-running animate-pulse',
    bgColor: 'bg-status-running/10',
  },
  waiting_approval: {
    label: 'Awaiting Approval',
    color: 'text-status-waiting',
    dotColor: 'bg-status-waiting animate-pulse',
    bgColor: 'bg-status-waiting/10',
  },
  completed: {
    label: 'Ready',
    color: 'text-status-running',
    dotColor: 'bg-status-running',
    bgColor: 'bg-status-running/10',
  },
  error: {
    label: 'Error',
    color: 'text-status-error',
    dotColor: 'bg-status-error',
    bgColor: 'bg-status-error/10',
  },
}
