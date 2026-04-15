import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { changePassword } from "@/lib/core-api"

export default function ChangePasswordPage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    if (next !== confirm) {
      setError("New password and confirmation do not match")
      return
    }
    if (next.length < 1) {
      setError("Enter a new password")
      return
    }
    setLoading(true)
    try {
      await changePassword(current, next)
      navigate("/")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md">
      <h1 className="text-2xl font-semibold tracking-tight mb-2">Change password</h1>
      <p className="text-sm text-muted-foreground mb-6">
        Enter your current password and choose a new one.
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="current">Current password</Label>
          <Input
            id="current"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="newp">New password</Label>
          <Input
            id="newp"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="confirm">Confirm new password</Label>
          <Input
            id="confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </div>
        {error ? (
          <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">{error}</div>
        ) : null}
        <div className="flex gap-2">
          <Button type="submit" disabled={loading}>
            {loading ? "Saving…" : "Update password"}
          </Button>
          <Button type="button" variant="outline" onClick={() => navigate(-1)}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  )
}
