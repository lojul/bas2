// AI providers a workspace can bring its own key for (bring-your-own-key).
export const AI_PROVIDERS = [
  { id: "anthropic", label: "Anthropic (Claude)", hint: "Starts with sk-ant-" },
  { id: "openrouter", label: "OpenRouter", hint: "Starts with sk-or-" },
  { id: "xai", label: "xAI (Grok)", hint: "Starts with xai-" },
  { id: "azure_openai", label: "Azure OpenAI", hint: "Key from your Azure OpenAI resource" },
] as const;

export type AiProviderId = (typeof AI_PROVIDERS)[number]["id"];

export const providerLabel = (id: string | null) => AI_PROVIDERS.find((p) => p.id === id)?.label ?? id ?? "—";
