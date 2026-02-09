import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import Button from './Button'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * Global error boundary — catches unhandled render errors and displays
 * a recovery UI instead of a white screen.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  private handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback

      return (
        <div className="flex items-center justify-center min-h-screen bg-zurk-900 p-6">
          <div className="text-center max-w-md space-y-4">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-status-error/10 border border-status-error/20 flex items-center justify-center">
              <svg className="w-7 h-7 text-status-error" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
            </div>

            <div>
              <h2 className="text-lg font-semibold text-zurk-100">Something went wrong</h2>
              <p className="text-sm text-zurk-400 mt-1">
                An unexpected error occurred. You can try recovering or reload the page.
              </p>
            </div>

            {this.state.error && (
              <div className="text-left bg-zurk-800 border border-zurk-700 rounded-lg p-3">
                <p className="text-xs font-mono text-status-error break-words">
                  {this.state.error.message}
                </p>
              </div>
            )}

            <div className="flex items-center justify-center gap-3">
              <Button variant="primary" size="md" onClick={this.handleReset}>
                Try Again
              </Button>
              <Button variant="secondary" size="md" onClick={this.handleReload}>
                Reload Page
              </Button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
