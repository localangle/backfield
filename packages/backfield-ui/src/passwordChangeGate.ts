export interface PasswordChangeGateState {
  loading: boolean
  isAuthenticated: boolean
  mustChangePassword: boolean
}

export function shouldForcePasswordChange({
  loading,
  isAuthenticated,
  mustChangePassword,
}: PasswordChangeGateState): boolean {
  return !loading && isAuthenticated && mustChangePassword
}
