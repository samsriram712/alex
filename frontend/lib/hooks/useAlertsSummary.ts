import { useEffect, useState } from "react"

export function useAlertsSummary() {
  const [summary, setSummary] = useState<{ unread_count: number }>({ unread_count: 0 })

  useEffect(() => {
    fetch("${process.env.NEXT_PUBLIC_API_URL}/api/alerts/summary", { credentials: "include" })
      .then(res => res.json())
      .then(setSummary)
      .catch(() => setSummary({ unread_count: 0 }))
  }, [])

  return summary
}