// Shown at once when moving between workspace pages, while the page is prepared on the server
// (also lets Next.js prefetch the page frame, so a click answers immediately).
export default function Loading() {
  return (
    <div className="animate-pulse space-y-4" aria-busy="true" aria-label="Loading">
      <div className="h-4 w-64 rounded bg-genie-accent" />
      <div className="h-28 rounded-lg bg-genie-accent/70" />
      <div className="h-28 rounded-lg bg-genie-accent/50" />
    </div>
  );
}
