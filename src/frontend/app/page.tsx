"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

export default function Home() {
  const router = useRouter()

  useEffect(() => {
    router.replace("/overview/")
  }, [router])

  return <p className="p-4 text-sm text-muted-foreground">Đang mở tổng quan...</p>
}
