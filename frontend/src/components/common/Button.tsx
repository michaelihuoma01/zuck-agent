import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const variantStyles: Record<Variant, string> = {
  primary:
    'bg-accent-600 text-zurk-900 hover:bg-accent-400 active:bg-accent-400/90',
  secondary:
    'bg-zurk-700/80 text-zurk-100 hover:bg-zurk-600 border border-zurk-600/80',
  danger:
    'bg-status-error/10 text-status-error hover:bg-status-error/20 border border-status-error/30',
  ghost:
    'bg-transparent text-zurk-300 hover:bg-zurk-700/70 hover:text-zurk-100',
}

const sizeStyles: Record<Size, string> = {
  sm: 'text-xs px-2.5 py-1.5 rounded-md',
  md: 'text-sm px-3.5 py-2 rounded-lg',
  lg: 'text-sm px-5 py-2.5 rounded-lg',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center font-medium transition-colors
        disabled:opacity-50 disabled:cursor-not-allowed shadow-[0_0_0_1px_rgba(255,255,255,0.06)]
        ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {loading && (
        <svg
          className="animate-spin -ml-1 mr-2 h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      )}
      {children}
    </button>
  )
}
