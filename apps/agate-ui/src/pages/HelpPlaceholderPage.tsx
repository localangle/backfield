export default function HelpPlaceholderPage() {
  return (
    <div className="w-full max-w-none space-y-2">
      <h1 className="text-2xl font-bold">Help</h1>
      <p className="text-muted-foreground">
        For now, visit the{' '}
        <a
          href="https://github.com/localangle/backfield/"
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-4 hover:text-foreground"
        >
          Backfield GitHub repository
        </a>{' '}
        for help.
      </p>
    </div>
  )
}
