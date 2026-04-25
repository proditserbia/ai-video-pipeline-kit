import { cn } from '@/lib/utils'
import { HTMLAttributes } from 'react'

interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'destructive' | 'success'
}

function Alert({ className, variant = 'default', ...props }: AlertProps) {
  return (
    <div
      role="alert"
      className={cn(
        'relative w-full rounded-lg border p-4',
        variant === 'default' && 'border-gray-700 bg-gray-800 text-gray-200',
        variant === 'destructive' && 'border-red-700 bg-red-900/20 text-red-400',
        variant === 'success' && 'border-green-700 bg-green-900/20 text-green-400',
        className
      )}
      {...props}
    />
  )
}

function AlertTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h5 className={cn('mb-1 font-medium leading-none tracking-tight', className)} {...props} />
}

function AlertDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <div className={cn('text-sm opacity-90', className)} {...props} />
}

export { Alert, AlertTitle, AlertDescription }
