import { BRAND } from "@/lib/brand";

// Details used on the Privacy Policy and Terms of Service pages.
// TO CONFIRM before relying on these pages: the registered company name, address and contact
// email. Have the final wording checked by a Hong Kong lawyer.
export const LEGAL = {
  entity: `${BRAND.company} Limited`,
  address: "Hong Kong",
  contactEmail: "privacy@infiniduo.com",
  supportEmail: "support@infiniduo.com",
  governingLaw: "the Hong Kong Special Administrative Region",
  lastUpdated: "15 October 2026",
  hosting: "Singapore",
} as const;
