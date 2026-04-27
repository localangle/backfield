import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export type ShowAppMessageOptions = {
  title?: string
  /** Use destructive styling for the title (errors). */
  variant?: "default" | "destructive"
}

export type ShowAppConfirmOptions = {
  title?: string
  confirmLabel?: string
  cancelLabel?: string
  /** Style the primary action as destructive (e.g. delete). */
  destructive?: boolean
}

type AppDialogState =
  | { kind: "closed" }
  | {
      kind: "message"
      title: string
      description: string
      variant: "default" | "destructive"
    }
  | {
      kind: "confirm"
      title: string
      description: string
      confirmLabel: string
      cancelLabel: string
      destructive: boolean
      resolve: (value: boolean) => void
    }

type AppMessageContextValue = {
  showMessage: (description: string, options?: ShowAppMessageOptions) => void
  showError: (description: string, options?: { title?: string }) => void
  showConfirm: (description: string, options?: ShowAppConfirmOptions) => Promise<boolean>
}

const AppMessageContext = createContext<AppMessageContextValue | null>(null)

export function useAppMessage(): AppMessageContextValue {
  const ctx = useContext(AppMessageContext)
  if (!ctx) {
    throw new Error("useAppMessage must be used within AppMessageProvider")
  }
  return ctx
}

export function AppMessageProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppDialogState>({ kind: "closed" })
  /** Avoid `onOpenChange(false)` racing confirm success and calling `resolve(false)`. */
  const suppressConfirmDismissRef = useRef(false)

  const close = useCallback(() => {
    if (suppressConfirmDismissRef.current) {
      suppressConfirmDismissRef.current = false
      setState({ kind: "closed" })
      return
    }
    setState((prev) => {
      if (prev.kind === "confirm") {
        prev.resolve(false)
      }
      return { kind: "closed" }
    })
  }, [])

  const showMessage = useCallback((description: string, options?: ShowAppMessageOptions) => {
    setState({
      kind: "message",
      title: options?.title ?? "Notice",
      description,
      variant: options?.variant ?? "default",
    })
  }, [])

  const showError = useCallback(
    (description: string, options?: { title?: string }) => {
      showMessage(description, { title: options?.title ?? "Error", variant: "destructive" })
    },
    [showMessage],
  )

  const showConfirm = useCallback((description: string, options?: ShowAppConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({
        kind: "confirm",
        title: options?.title ?? "Confirm",
        description,
        confirmLabel: options?.confirmLabel ?? "Continue",
        cancelLabel: options?.cancelLabel ?? "Cancel",
        destructive: options?.destructive ?? false,
        resolve,
      })
    })
  }, [])

  const value = useMemo(
    () => ({
      showMessage,
      showError,
      showConfirm,
    }),
    [showConfirm, showError, showMessage],
  )

  const open = state.kind !== "closed"

  return (
    <AppMessageContext.Provider value={value}>
      {children}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) close()
        }}
      >
        <DialogContent className="sm:max-w-md" onPointerDownOutside={(e) => e.preventDefault()}>
          {state.kind === "message" ? (
            <>
              <DialogHeader>
                <DialogTitle
                  className={state.variant === "destructive" ? "text-destructive" : undefined}
                >
                  {state.title}
                </DialogTitle>
                <DialogDescription className="text-left whitespace-pre-wrap break-words">
                  {state.description}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button type="button" onClick={() => setState({ kind: "closed" })}>
                  OK
                </Button>
              </DialogFooter>
            </>
          ) : null}
          {state.kind === "confirm" ? (
            <>
              <DialogHeader>
                <DialogTitle>{state.title}</DialogTitle>
                <DialogDescription className="text-left whitespace-pre-wrap break-words">
                  {state.description}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="gap-2 sm:gap-0">
                <Button type="button" variant="outline" onClick={close}>
                  {state.cancelLabel}
                </Button>
                <Button
                  type="button"
                  variant={state.destructive ? "destructive" : "default"}
                  onClick={() => {
                    suppressConfirmDismissRef.current = true
                    const r = state.resolve
                    setState({ kind: "closed" })
                    r(true)
                  }}
                >
                  {state.confirmLabel}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </AppMessageContext.Provider>
  )
}
