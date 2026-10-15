// Safe to import from client components (no server-only code).
export type Role = "owner" | "admin" | "member" | "viewer";

export const ROLE_LABEL: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
  viewer: "Viewer",
};

export const canManage = (role: Role) => role === "owner" || role === "admin";
