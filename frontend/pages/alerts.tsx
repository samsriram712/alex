import { useEffect, useState } from "react"
import Head from "next/head"
import Layout from '../components/Layout'
import { useAuth } from "@clerk/nextjs"

type Alert = {
  alert_id: string
  domain: string
  category: string
  severity: "info" | "warning" | "critical"
  title: string
  message: string
  rationale?: string
  status: "new" | "read" | "dismissed"
  created_at: string
}

export default function AlertsPage() {
  const { getToken } = useAuth()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [domain, setDomain] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [showDismissed, setShowDismissed] = useState(false)

  useEffect(() => {
    loadAlerts()
  }, [domain, showDismissed])

  async function loadAlerts() {
    setLoading(true)
  
    let url = `${process.env.NEXT_PUBLIC_API_URL}/api/alerts`
    const params = new URLSearchParams()

    if (domain) params.append("domain", domain)
    if (showDismissed) params.append("include_dismissed", "true")

    if (params.toString()) url += `?${params.toString()}`
  
    const token = await getToken()

    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    })
  
    // Handle auth failure cleanly
    if (res.status === 403 || res.status === 401) {
      console.warn("Not authenticated")
      setAlerts([])
      setLoading(false)
      return
    }
  
    const data = await res.json()
  
    // Guard: ensure array
    if (!Array.isArray(data)) {
      console.error("Unexpected alerts response:", data)
      setAlerts([])
    } else {
      setAlerts(data)
    }
  
    setLoading(false)
  }
  

  async function markAsRead(alertId: string) {
    const token = await getToken()

    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/alerts/${alertId}?status=read`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`
      }
    })

    loadAlerts()
  }

  async function dismissAlert(alertId: string) {
    const token = await getToken()
    
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/alerts/${alertId}?status=dismissed`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`
      }
    })
    
    loadAlerts()
  }

  return (
    <>
      <Head>
        <title>Alerts | Alex</title>
      </Head>

      <Layout>
      <div className="min-h-screen bg-gray-50 py-8">
      {/* MAIN CONTENT WRAPPER – does NOT interfere with layout/header */}
       <div className="max-w-7xl mx-auto px-6 py-8">
        {/*bg-white rounded-lg shadow px-8 py-6 mb-8*/}
        {/* PAGE HEADER ROW */}
        {/*<div className="flex items-center justify-between mb-6">*/}
        <div className="bg-white rounded-lg shadow px-8 py-6 mb-8">

          {/* <div> */}
            {/* <h1 className="text-2xl font-bold">Alerts</h1> */}
            {/* <p className="text-gray-500 text-sm"> */}
              {/* System notifications and portfolio insights */}
            {/* </p> */}
          {/* </div> */}

          {/*<div className="bg-white rounded-lg shadow px-8 py-6 mb-8">*/}
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold text-dark mb-2">Alerts</h1>
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
          </select>

          <label style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "12px" }}>
            <input
              type="checkbox"
              checked={showDismissed}
              onChange={(e) => setShowDismissed(e.target.checked)}
            />
            Show dismissed
          </label>


        </div>

        {/* LOADING STATE */}
        {loading && (
          <p className="text-gray-500">Loading alerts...</p>
        )}

        {/* EMPTY STATE */}
        {!loading && alerts.length === 0 && (
          <p className="text-gray-500">No alerts 🎉</p>
        )}

        {/* ALERT LIST */}
        <div className="alert-list space-y-4">
          {Array.isArray(alerts) && alerts.map(alert => (
            <div
              key={alert.alert_id}
              className={`alert-card ${alert.severity}`}
            >

              <div className="alert-header">
                <span className={`pill ${alert.domain}`}>
                  {alert.domain}
                </span>

                <span className={`severity ${alert.severity}`}>
                  {alert.severity.toUpperCase()}
                </span>

                {alert.status !== "dismissed" && (
                  <div
                    className="actions"
                    style={{ display: "flex", alignItems: "center", gap: "8px" }}
                  >
                    {alert.status === "new" && (
                      <button
                        onClick={() => markAsRead(alert.alert_id)}
                        className="mark-read"
                      >
                        Mark as read
                      </button>
                    )}

                    <button
                      onClick={() => dismissAlert(alert.alert_id)}
                      className="mark-read"
                      style={{ backgroundColor: "#6b7280", color: "white" }}
                    >
                      Dismiss
                    </button>
                  </div>
                )}

              </div>

              <h3>{alert.title}</h3>
              <p>{alert.message}</p>

              {alert.rationale && (
                <div className="rationale">
                  {alert.rationale}
                </div>
              )}

              <div className="timestamp">
                {new Date(alert.created_at).toLocaleString()}
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
