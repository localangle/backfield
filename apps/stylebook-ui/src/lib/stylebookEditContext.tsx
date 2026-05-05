import { createContext, useContext, type ReactNode } from "react"

type StylebookEditContextValue = {
  canEditStylebook: boolean
}

const StylebookEditContext = createContext<StylebookEditContextValue>({
  canEditStylebook: false,
})

export function StylebookEditProvider({
  canEditStylebook,
  children,
}: {
  canEditStylebook: boolean
  children: ReactNode
}) {
  return (
    <StylebookEditContext.Provider value={{ canEditStylebook }}>
      {children}
    </StylebookEditContext.Provider>
  )
}

export function useCanEditStylebook(): boolean {
  return useContext(StylebookEditContext).canEditStylebook
}

