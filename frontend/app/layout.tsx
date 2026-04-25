import type { Metadata } from 'next'
import './globals.css'
import QueryProvider from '@/providers/QueryProvider'

export const metadata: Metadata = {
  title: 'AI Video Pipeline',
  description: 'AI Video Production Factory Dashboard',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-900 text-white antialiased">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  )
}
