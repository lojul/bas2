"use client";

import { useActionState, useState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { createWorkspace } from "./actions";

function toSlug(name: string) {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
}

export function NewWorkspaceForm() {
  const [state, action] = useActionState(createWorkspace, undefined);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);

  return (
    <form action={action} className="space-y-4">
      <div>
        <label htmlFor="name" className="label">Company name</label>
        <input
          id="name" name="name" required className="input" placeholder="Acme Property Ltd"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (!slugEdited) setSlug(toSlug(e.target.value));
          }}
        />
      </div>
      <div>
        <label htmlFor="slug" className="label">Workspace address</label>
        <div className="flex items-center gap-1 text-sm">
          <span className="text-genie-muted">/app/</span>
          <input
            id="slug" name="slug" required className="input" placeholder="acme"
            value={slug}
            onChange={(e) => {
              setSlugEdited(true);
              setSlug(e.target.value.toLowerCase());
            }}
          />
        </div>
        <p className="mt-1 text-xs text-genie-muted">Lowercase letters, numbers and dashes. Used in links to this workspace.</p>
      </div>
      <SubmitButton pendingText="Creating…">Create workspace</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
