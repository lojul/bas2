// Models a workspace can choose for Ask, per provider route (safe for client components).
// The platform OpenRouter account is in Hong Kong, so its list only has models that serve Hong
// Kong; with the workspace's own OpenRouter key any OpenRouter model id can be typed in.
export type RouteProvider = "anthropic" | "openrouter" | "xai";
export type ModelOption = { id: string; label: string; note: string };

export const BYOK_ORDER: RouteProvider[] = ["anthropic", "openrouter", "xai"];

export const MODEL_OPTIONS: Record<RouteProvider, ModelOption[]> = {
  anthropic: [
    { id: "claude-opus-5-5", label: "Claude Opus 5.5", note: "best answers" },
    { id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5", note: "fast, strong" },
    { id: "claude-haiku-5-5", label: "Claude Haiku 5.5", note: "fastest, cheapest" },
  ],
  openrouter: [
    { id: "qwen/qwen3.8-max-0902", label: "Qwen 3.8 Max", note: "default · strong, English and Chinese" },
    { id: "qwen/qwen3.8-flash", label: "Qwen 3.8 Flash", note: "much faster and cheaper" },
    { id: "deepseek/deepseek-v4-pro-0813", label: "DeepSeek V4 Pro", note: "strong, low cost" },
    { id: "deepseek/deepseek-v4.1-flash", label: "DeepSeek V4.1 Flash", note: "fast, very cheap" },
    { id: "z-ai/glm-5.3", label: "GLM 5.3", note: "strong, low cost" },
    { id: "moonshotai/kimi-k3", label: "Kimi K3", note: "long answers" },
    { id: "x-ai/grok-4.7", label: "Grok 4.7", note: "xAI via OpenRouter" },
    { id: "mistralai/mistral-large-4-0", label: "Mistral Large 4", note: "European provider" },
  ],
  xai: [
    { id: "grok-4.7", label: "Grok 4.7", note: "newest" },
    { id: "grok-4.6", label: "Grok 4.6", note: "" },
  ],
};

export const PROVIDER_NAME: Record<RouteProvider, string> = { anthropic: "Anthropic", openrouter: "OpenRouter", xai: "xAI" };

// A model id typed in by hand: letters, digits and . - _ / : only.
export const validModelId = (id: string) => /^[A-Za-z0-9._:/-]{2,100}$/.test(id);

// tenants.settings.ai_models: the chosen model per provider route.
export type AiModelSettings = Partial<Record<RouteProvider, string>>;
