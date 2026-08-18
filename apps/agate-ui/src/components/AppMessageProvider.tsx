import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { Loader2 } from "lucide-react"
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
  /** When true, OK and closing the dialog are disabled until updated or dismissed via the handle. */
  pending?: boolean
}

export type MessageDialogHandle = {
  update: (description: string, options?: Pick<ShowAppMessageOptions, "title" | "variant" | "pending">) => void
  dismiss: () => void
}

export type ShowAppConfirmOptions = {
  title?: string
  confirmLabel?: string
  cancelLabel?: string
  /** Style the primary action as destructive (e.g. delete). */
  destructive?: boolean
}

export type ConfirmChoice = "primary" | "secondary" | false

export type ShowAppConfirmChoiceOptions = {
  title?: string
  primaryLabel: string
  secondaryLabel: string
  cancelLabel?: string
  primaryDestructive?: boolean
  secondaryDestructive?: boolean
}

type AppDialogState =
  | { kind: "closed" }
  | {
      kind: "message"
      title: string
      description: string
      variant: "default" | "destructive"
      pending: boolean
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
  | {
      kind: "confirm_choice"
      title: string
      description: string
      primaryLabel: string
      secondaryLabel: string
      cancelLabel: string
      primaryDestructive: boolean
      secondaryDestructive: boolean
      resolve: (value: ConfirmChoice) => void
    }

type AppMessageContextValue = {
  showMessage: (description: string, options?: ShowAppMessageOptions) => MessageDialogHandle
  showError: (description: string, options?: { title?: string }) => void
  showConfirm: (description: string, options?: ShowAppConfirmOptions) => Promise<boolean>
  showConfirmChoice: (
    description: string,
    options: ShowAppConfirmChoiceOptions,
  ) => Promise<ConfirmChoice>
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
      if (prev.kind === "confirm_choice") {
        prev.resolve(false)
      }
      return { kind: "closed" }
    })
  }, [])

  const showMessage = useCallback((description: string, options?: ShowAppMessageOptions): MessageDialogHandle => {
    setState({
      kind: "message",
      title: options?.title ?? "Notice",
      description,
      variant: options?.variant ?? "default",
      pending: options?.pending ?? false,
    })
    return {
      update: (d, o) => {
        setState((prev) => {
          if (prev.kind !== "message") return prev
          return {
            ...prev,
            description: d,
            title: o?.title !== undefined ? o.title : prev.title,
            variant: o?.variant !== undefined ? o.variant : prev.variant,
            pending: o?.pending !== undefined ? o.pending : prev.pending,
          }
        })
      },
      dismiss: () => setState({ kind: "closed" }),
    }
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

  const showConfirmChoice = useCallback(
    (description: string, options: ShowAppConfirmChoiceOptions): Promise<ConfirmChoice> => {
      return new Promise((resolve) => {
        setState({
          kind: "confirm_choice",
          title: options.title ?? "Confirm",
          description,
          primaryLabel: options.primaryLabel,
          secondaryLabel: options.secondaryLabel,
          cancelLabel: options.cancelLabel ?? "Cancel",
          primaryDestructive: options.primaryDestructive ?? false,
          secondaryDestructive: options.secondaryDestructive ?? false,
          resolve,
        })
      })
    },
    [],
  )

  const value = useMemo(
    () => ({
      showMessage,
      showError,
      showConfirm,
      showConfirmChoice,
    }),
    [showConfirm, showConfirmChoice, showError, showMessage],
  )

  const open = state.kind !== "closed"

  return (
    <AppMessageContext.Provider value={value}>
      {children}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) {
            if (state.kind === "message" && state.pending) {
              return
            }
            close()
          }
        }}
      >
        <DialogContent
          className={state.kind === "confirm_choice" ? "sm:max-w-lg" : "sm:max-w-md"}
          hideCloseButton={state.kind === "message" && state.pending}
          onPointerDownOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => {
            if (state.kind === "message" && state.pending) {
              e.preventDefault()
            }
          }}
        >
          {state.kind === "message" ? (
            <>
              <DialogHeader>
                <DialogTitle
                  className={state.variant === "destructive" ? "text-destructive" : undefined}
                >
                  {state.title}
                </DialogTitle>
                {state.pending ? (
                  <div
                    className="flex items-start gap-3 text-left text-sm text-muted-foreground"
                    role="status"
                    aria-live="polite"
                    aria-busy
                  >
                    <Loader2
                      className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-muted-foreground"
                      aria-hidden
                    />
                    <DialogDescription className="text-left whitespace-pre-wrap break-words !mt-0">
                      {state.description}
                    </DialogDescription>
                  </div>
                ) : (
                  <DialogDescription className="text-left whitespace-pre-wrap break-words">
                    {state.description}
                  </DialogDescription>
                )}
              </DialogHeader>
              <DialogFooter>
                <Button
                  type="button"
                  disabled={state.pending}
                  onClick={() => setState({ kind: "closed" })}
                >
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
          {state.kind === "confirm_choice" ? (
            <>
              <DialogHeader>
                <DialogTitle>{state.title}</DialogTitle>
                <DialogDescription className="text-left whitespace-pre-wrap break-words">
                  {state.description}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="gap-2 sm:flex-wrap">
                <Button type="button" variant="outline" onClick={close}>
                  {state.cancelLabel}
                </Button>
                <Button
                  type="button"
                  variant={state.primaryDestructive ? "destructive" : "default"}
                  onClick={() => {
                    suppressConfirmDismissRef.current = true
                    const r = state.resolve
                    setState({ kind: "closed" })
                    r("primary")
                  }}
                >
                  {state.primaryLabel}
                </Button>
                <Button
                  type="button"
                  variant={state.secondaryDestructive ? "destructive" : "secondary"}
                  onClick={() => {
                    suppressConfirmDismissRef.current = true
                    const r = state.resolve
                    setState({ kind: "closed" })
                    r("secondary")
                  }}
                >
                  {state.secondaryLabel}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </AppMessageContext.Provider>
  )
}
