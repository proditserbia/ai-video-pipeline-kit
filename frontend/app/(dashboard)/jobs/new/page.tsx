'use client'
import Link from 'next/link'
import CreateJobForm from '@/components/jobs/CreateJobForm'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ArrowLeft } from 'lucide-react'

export default function NewJobPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-4">
        <Button asChild variant="ghost" size="sm">
          <Link href="/jobs"><ArrowLeft className="mr-2 h-4 w-4" />Back</Link>
        </Button>
        <h1 className="text-2xl font-bold text-white">Create New Job</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Job Details</CardTitle>
        </CardHeader>
        <CardContent>
          <CreateJobForm />
        </CardContent>
      </Card>
    </div>
  )
}
