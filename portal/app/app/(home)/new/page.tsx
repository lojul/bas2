import type { Metadata } from "next";
import { BRAND } from "@/lib/brand";
import { NewWorkspaceForm } from "./new-workspace-form";

export const metadata: Metadata = { title: "New workspace" };

export default function NewWorkspacePage() {
  return (
    <div className="mx-auto max-w-lg">
      <h1 className="text-2xl font-semibold">Create your workspace</h1>
      <p className="mt-1 text-sm text-genie-muted">
        A workspace holds one company&apos;s data, people and settings in {BRAND.name}. You&apos;ll be its owner.
      </p>
      <div className="card mt-6">
        <NewWorkspaceForm />
      </div>
    </div>
  );
}
