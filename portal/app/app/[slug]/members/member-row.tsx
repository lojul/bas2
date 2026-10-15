"use client";

import { useActionState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { type Role, ROLE_LABEL } from "@/lib/roles";
import { changeRole, removeMember } from "./actions";

type Props = {
  slug: string;
  member: { user_id: string; email: string; role: Role; joined_at: string };
  isSelf: boolean;
  myRole: Role;
};

export function MemberRow({ slug, member, isSelf, myRole }: Props) {
  const [roleState, roleAction] = useActionState(changeRole, undefined);
  const [removeState, removeAction] = useActionState(removeMember, undefined);

  // Owners manage everyone; admins manage non-owners and cannot make owners.
  const canEdit = myRole === "owner" || (myRole === "admin" && member.role !== "owner");
  const roleChoices: Role[] = myRole === "owner" ? ["owner", "admin", "member", "viewer"] : ["admin", "member", "viewer"];

  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium">
            {member.email} {isSelf && <span className="text-genie-muted">(you)</span>}
          </div>
          <div className="text-xs text-genie-muted">Joined {new Date(member.joined_at).toLocaleDateString()}</div>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && !isSelf ? (
            <form action={roleAction} className="flex items-center gap-2">
              <input type="hidden" name="slug" value={slug} />
              <input type="hidden" name="user_id" value={member.user_id} />
              <select name="role" defaultValue={member.role} className="input w-auto py-1">
                {roleChoices.map((r) => (
                  <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                ))}
              </select>
              <SubmitButton className="btn-secondary px-3 py-1" pendingText="…">Save</SubmitButton>
            </form>
          ) : (
            <span className="text-sm text-genie-muted">{ROLE_LABEL[member.role]}</span>
          )}
          {(canEdit || isSelf) && (
            <form
              action={removeAction}
              onSubmit={(e) => {
                const msg = isSelf ? "Leave this workspace?" : `Remove ${member.email} from this workspace?`;
                if (!confirm(msg)) e.preventDefault();
              }}
            >
              <input type="hidden" name="slug" value={slug} />
              <input type="hidden" name="user_id" value={member.user_id} />
              <SubmitButton className="btn-danger" pendingText="…">{isSelf ? "Leave" : "Remove"}</SubmitButton>
            </form>
          )}
        </div>
      </div>
      <FormMessage state={roleState?.error ? roleState : removeState} />
    </li>
  );
}
