import { useState, type FormEvent } from "react"

export interface ForcedPasswordChangeProps {
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  onComplete: () => Promise<void> | void
  onLogout: () => Promise<void> | void
}

export function ForcedPasswordChange({
  changePassword,
  onComplete,
  onLogout,
}: ForcedPasswordChangeProps) {
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError("")
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match.")
      return
    }
    setSubmitting(true)
    try {
      await changePassword(currentPassword, newPassword)
      await onComplete()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not change password.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <section
        className="w-full max-w-md rounded-lg border bg-white p-6 shadow-sm"
        aria-labelledby="required-password-heading"
      >
        <h1 id="required-password-heading" className="text-2xl font-semibold tracking-tight">
          Choose a new password
        </h1>
        <p className="mt-2 text-sm text-gray-600">
          Replace your temporary password before continuing.
        </p>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium" htmlFor="current-password">
            Temporary password
          </label>
          <input
            id="current-password"
            className="block w-full rounded-md border px-3 py-2"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            required
            autoFocus
          />
          <label className="block text-sm font-medium" htmlFor="new-password">
            New password
          </label>
          <input
            id="new-password"
            className="block w-full rounded-md border px-3 py-2"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            required
          />
          <label className="block text-sm font-medium" htmlFor="confirm-password">
            Confirm new password
          </label>
          <input
            id="confirm-password"
            className="block w-full rounded-md border px-3 py-2"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
          />
          {error ? (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          ) : null}
          <button
            className="w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "Saving…" : "Save new password"}
          </button>
          <button
            className="w-full rounded-md border px-4 py-2 text-sm font-medium"
            type="button"
            onClick={() => void onLogout()}
            disabled={submitting}
          >
            Log out
          </button>
        </form>
      </section>
    </main>
  )
}
