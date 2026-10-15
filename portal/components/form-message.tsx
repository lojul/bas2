export type FormState = { error?: string; ok?: string } | undefined;

export function FormMessage({ state }: { state: FormState }) {
  if (state?.error) return <p className="mt-3 text-sm text-genie-danger">{state.error}</p>;
  if (state?.ok) return <p className="mt-3 text-sm text-genie-green-deep">{state.ok}</p>;
  return null;
}
