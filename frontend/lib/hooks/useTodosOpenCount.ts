import { useEffect, useState } from "react"

export function useTodosOpenCount() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    fetch("${process.env.NEXT_PUBLIC_API_URL}/api/todos?status=open", { credentials: "include" })
      .then(res => res.json())
      .then(rows => setCount(rows.length))
      .catch(() => setCount(0))
  }, [])

  return count
}
