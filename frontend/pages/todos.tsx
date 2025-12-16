import { useEffect, useState } from "react"
import Head from "next/head"
import Layout from '../components/Layout'
import { useAuth } from "@clerk/nextjs"

type Todo = {
  todo_id: string
  domain: string
  category: string
  priority: "low" | "medium" | "high"
  title: string
  description: string
  status: "open" | "done" | "in_progress"
  created_at: string
}

export default function TodosPage() {
  const { getToken } = useAuth()
  const [todos, setTodos] = useState<Todo[]>([])
  const [domain, setDomain] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadTodos()
  }, [domain])

  async function loadTodos() {
    setLoading(true)

    let url = `${process.env.NEXT_PUBLIC_API_URL}/api/todos`
    if (domain) url += `?domain=${domain}`

    const token = await getToken()

    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    })

    if (res.status === 401 || res.status === 403) {
      console.warn("Not authenticated")
      setTodos([])
      setLoading(false)
      return
    }

    const data = await res.json()

    if (!Array.isArray(data)) {
      console.error("Unexpected todos response:", data)
      setTodos([])
    } else {
      setTodos(data)
    }

    setLoading(false)
  }

  async function updateStatus(todoId: string, status: "done" | "in_progress") {
    
    const token = await getToken()

    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/todos/${todoId}?status=${status}`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`
      }
    })

    loadTodos()
  }

  return (
    <>
      <Head>
        <title>Tasks | Alex</title>
      </Head>

      <Layout>
      <div className="min-h-screen bg-gray-50 py-8">
       <div className="max-w-7xl mx-auto px-6 py-8">

        <div className="bg-white rounded-lg shadow px-8 py-6 mb-8">
          
         <div className="flex items-center justify-between">
          <h1 className="text-3xl font-bold">Tasks</h1>
          <p className="text-2xl font-bold">
              System notifications and portfolio insights
          </p>
         </div>

          <select
            value={domain ?? ""}
            onChange={(e) => setDomain(e.target.value || null)}
            className="filter"
          >
            <option value="">All Domains</option>
            <option value="portfolio">Portfolio</option>
            <option value="retirement">Retirement</option>
            <option value="research">Research</option>
            <option value="system">System</option>
          </select>
        </div>

        {loading && (<p className="text-gray-500">Loading tasks...</p>)}

        {!loading && todos.length === 0 && (
          <p className="text-gray-500">No tasks ✅</p>
        )}

        <div className="alert-list space-y-4">
          {Array.isArray(todos) && todos.map(todo => (
            <div
              key={todo.todo_id}
              className={`alert-card ${todo.priority}`}
            >
              <div className="alert-header">
                <span className={`pill ${todo.domain}`}>
                  {todo.domain}
                </span>

                <span className={`severity ${todo.priority}`}>
                  {todo.priority.toUpperCase()}
                </span>

                {todo.status !== "done" && (
                  <div className="actions" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    {/* State indicator (not clickable) */}
                    {todo.status === "in_progress" && (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "4px 10px",
                          borderRadius: "9999px",
                          fontSize: "0.85rem",
                          fontWeight: 500,
                          backgroundColor: "#dcfce7", // green-100
                          color: "#166534" // green-800
                        }}
                      >
                        🔄 In Progress
                      </span>
                    )}


                    {todo.status === "open" && (
                      <button
                        onClick={() => updateStatus(todo.todo_id, "in_progress")}
                        className="mark-read"
                        style={{
                          /* marginLeft: "8px", */
                          backgroundColor: "#16a34a",
                          color: "white"
                        }}
                      >
                        🔄 Start
                      </button>
                    )}

                    <button
                      onClick={() => updateStatus(todo.todo_id, "done")}
                      className="mark-read"
                      /* style={{ marginLeft: todo.status === "open" ? "8px" : "0" }} */
                    >
                      ✅ Done
                    </button>
                  </div>
                )}



              </div>

              <h3>{todo.title}</h3>
              <p>{todo.description}</p>

              <div className="timestamp">
                {new Date(todo.created_at).toLocaleString()}
              </div>

            </div>
          ))}
        </div>

       </div>
      </div>
      </Layout>
    </>
  )
}
