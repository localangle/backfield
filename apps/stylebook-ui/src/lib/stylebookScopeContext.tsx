import { createContext, useContext, type ReactNode } from "react"

const StylebookScopeContext = createContext<string>("Stylebook")

export function StylebookScopeProvider({
  selectedStylebookLabel,
  children,
}: {
  selectedStylebookLabel: string
  children: ReactNode
}) {
  return (
    <StylebookScopeContext.Provider value={selectedStylebookLabel}>
      {children}
    </StylebookScopeContext.Provider>
  )
}

export function useSelectedStylebookLabel(): string {
  return useContext(StylebookScopeContext)
}
