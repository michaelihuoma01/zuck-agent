import type { InputHTMLAttributes } from 'react'
import { forwardRef } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-')

    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-zurk-200"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`w-full bg-zurk-800/80 border border-zurk-600/70 rounded-lg px-3 py-2 text-sm
            text-zurk-100 placeholder:text-zurk-500
            focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-400
            disabled:opacity-50 disabled:cursor-not-allowed
            ${error ? 'border-status-error focus:ring-status-error/40 focus:border-status-error' : ''}
            ${className}`}
          {...props}
        />
        {error && <p className="text-xs text-status-error">{error}</p>}
      </div>
    )
  },
)

Input.displayName = 'Input'
export default Input
