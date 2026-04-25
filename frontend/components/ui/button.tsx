'use client'
import { cn } from '@/lib/utils'
import { ButtonHTMLAttributes, forwardRef, cloneElement, isValidElement, ReactElement } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  isLoading?: boolean
  asChild?: boolean
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', isLoading, children, disabled, asChild, ...props }, ref) => {
    const classes = cn(
      'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50 disabled:pointer-events-none',
      variant === 'default' && 'bg-blue-600 text-white hover:bg-blue-700',
      variant === 'destructive' && 'bg-red-600 text-white hover:bg-red-700',
      variant === 'outline' && 'border border-gray-600 bg-transparent text-gray-200 hover:bg-gray-700',
      variant === 'secondary' && 'bg-gray-700 text-gray-200 hover:bg-gray-600',
      variant === 'ghost' && 'bg-transparent text-gray-200 hover:bg-gray-700',
      variant === 'link' && 'bg-transparent text-blue-400 underline-offset-4 hover:underline p-0',
      size === 'default' && 'h-10 px-4 py-2 text-sm',
      size === 'sm' && 'h-8 px-3 text-xs',
      size === 'lg' && 'h-12 px-6 text-base',
      size === 'icon' && 'h-10 w-10',
      className
    )

    if (asChild && isValidElement(children)) {
      return cloneElement(children as ReactElement<{ className?: string }>, { className: cn(classes, (children as ReactElement<{ className?: string }>).props.className) })
    }

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={classes}
        {...props}
      >
        {isLoading ? (
          <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : null}
        {children}
      </button>
    )
  }
)
Button.displayName = 'Button'

export { Button }
