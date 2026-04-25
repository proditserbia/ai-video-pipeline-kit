import { cn } from '@/lib/utils'
import { HTMLAttributes } from 'react'

interface BadgeProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'
}

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors',
        variant === 'default' && 'bg-blue-600 text-white',
        variant === 'secondary' && 'bg-gray-700 text-gray-200',
        variant === 'destructive' && 'bg-red-600 text-white',
        variant === 'outline' && 'border border-gray-600 text-gray-300',
        variant === 'success' && 'bg-green-700 text-green-100',
        variant === 'warning' && 'bg-yellow-700 text-yellow-100',
        className
      )}
      {...props}
    />
  )
}

export { Badge }
