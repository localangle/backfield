interface PlaygroundMarkProps {
  className?: string
}

export default function PlaygroundMark({ className }: PlaygroundMarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="18" height="18" x="3" y="3" rx="2" />
      <path d="m8 9 3 3-3 3" />
      <path d="M13 15h3" />
    </svg>
  )
}
