import "server-only";
import Anthropic from "@anthropic-ai/sdk";
import { createAdminClient } from "@/lib/supabase/admin";
import type { ToolSpec } from "./tools";

// Model gateway: picks the AI provider and key for a workspace, then runs one tool-use loop on it.
// Order: the workspace's own key (Anthropic, then OpenRouter, then xAI), else the platform key
// (OPENROUTER_API_KEY only; there is no platform Anthropic key). Workspace keys are read from Supabase Vault with
// the service role; they never reach the browser.

export type ProviderId = "anthropic" | "openrouter" | "xai";
export type KeySource = "byok" | "platform";
export type Route = { provider: ProviderId; apiKey: string; model: string; keySource: KeySource };

export type ChatTurn = { role: "user" | "assistant"; content: string };
export type ToolRunner = (name: string, input: Record<string, unknown>) => Promise<unknown>;
export type LoopResult = {
  text: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  toolCalls: string[];
  stopped?: "max_steps" | "refusal";
};

// The platform OpenRouter account is registered in Hong Kong, where Anthropic, OpenAI and Google
// refuse service (OpenRouter 403 "violation of provider Terms Of Service", 2026-10-16). So the
// OpenRouter route sends a list: GENIE_OPENROUTER_MODEL first (comma-separated allowed), then models
// that serve Hong Kong; OpenRouter moves to the next one when a model is refused or down.
const OPENROUTER_HK_MODELS = ["qwen/qwen3.8-max-0902", "deepseek/deepseek-v4-pro-0813", "z-ai/glm-5.3"];
const OPENROUTER_MAX_MODELS = 3;

function openRouterModels(): string[] {
  const configured = (process.env.GENIE_OPENROUTER_MODEL ?? "").split(",").map((m) => m.trim()).filter(Boolean);
  return [...new Set([...configured, ...OPENROUTER_HK_MODELS])].slice(0, OPENROUTER_MAX_MODELS);
}

const MODELS: Record<ProviderId, string> = {
  anthropic: process.env.GENIE_ANTHROPIC_MODEL ?? "claude-opus-5-5",
  openrouter: openRouterModels().join(","),
  xai: process.env.GENIE_XAI_MODEL ?? "grok-4",
};
const BYOK_ORDER: ProviderId[] = ["anthropic", "openrouter", "xai"];
const MAX_STEPS = 8;
const MAX_TOKENS = 4096;

export class GatewayError extends Error {}

export async function resolveRoute(tenantId: string): Promise<Route> {
  const admin = createAdminClient();
  for (const provider of BYOK_ORDER) {
    const { data, error } = await admin.rpc("get_tenant_secret", { p_tenant_id: tenantId, p_name: `ai_${provider}` });
    if (error) throw new GatewayError(`Could not read workspace AI keys: ${error.message}`);
    if (typeof data === "string" && data) return { provider, apiKey: data, model: MODELS[provider], keySource: "byok" };
  }
  if (process.env.OPENROUTER_API_KEY) {
    return { provider: "openrouter", apiKey: process.env.OPENROUTER_API_KEY, model: MODELS.openrouter, keySource: "platform" };
  }
  throw new GatewayError(
    "No AI key available: add one under Settings → AI model keys, or set OPENROUTER_API_KEY on the server.",
  );
}

export function runLoop(route: Route, system: string, history: ChatTurn[], tools: ToolSpec[], run: ToolRunner) {
  return route.provider === "anthropic"
    ? runAnthropic(route, system, history, tools, run)
    : runOpenAICompatible(route, system, history, tools, run);
}

// ---------------------------------------------------------------------------
// Anthropic (official SDK). Server-side fallbacks retry a declined request on Anthropic's
// recommended fallback model instead of returning the refusal.
// ---------------------------------------------------------------------------
async function runAnthropic(route: Route, system: string, history: ChatTurn[], tools: ToolSpec[], run: ToolRunner) {
  const client = new Anthropic({ apiKey: route.apiKey });
  const messages: Anthropic.Beta.BetaMessageParam[] = history.map((t) => ({ role: t.role, content: t.content }));
  const result: LoopResult = { text: "", model: route.model, inputTokens: 0, outputTokens: 0, toolCalls: [] };

  for (let step = 0; step < MAX_STEPS; step++) {
    const response = await client.beta.messages.create({
      model: route.model,
      max_tokens: MAX_TOKENS,
      system,
      tools,
      messages,
      thinking: { type: "adaptive" },
      output_config: { effort: "medium" },
      fallbacks: "default",
      betas: ["server-side-fallback-2026-07-01"],
    });
    result.model = response.model;
    result.inputTokens += response.usage.input_tokens + (response.usage.cache_read_input_tokens ?? 0);
    result.outputTokens += response.usage.output_tokens;

    if (response.stop_reason === "refusal") {
      result.stopped = "refusal";
      result.text = "Sorry — the AI model declined to answer this request.";
      return result;
    }
    // Keep the full content (thinking blocks included) so the next turn stays valid.
    messages.push({ role: "assistant", content: response.content });

    if (response.stop_reason === "pause_turn") continue;
    if (response.stop_reason !== "tool_use") {
      result.text = response.content
        .flatMap((b) => (b.type === "text" ? [b.text] : []))
        .join("")
        .trim();
      return result;
    }

    const toolResults: Anthropic.Beta.BetaToolResultBlockParam[] = [];
    for (const block of response.content) {
      if (block.type !== "tool_use") continue;
      result.toolCalls.push(block.name);
      try {
        const output = await run(block.name, (block.input ?? {}) as Record<string, unknown>);
        toolResults.push({ type: "tool_result", tool_use_id: block.id, content: JSON.stringify(output) });
      } catch (e) {
        toolResults.push({ type: "tool_result", tool_use_id: block.id, content: errorText(e), is_error: true });
      }
    }
    messages.push({ role: "user", content: toolResults });
  }
  result.stopped = "max_steps";
  result.text = "I couldn't finish within the step limit. Try a narrower question.";
  return result;
}

// ---------------------------------------------------------------------------
// OpenRouter and xAI: OpenAI-compatible chat completions with function calling.
// ---------------------------------------------------------------------------
const BASE_URL: Record<Exclude<ProviderId, "anthropic">, string> = {
  openrouter: "https://openrouter.ai/api/v1",
  xai: "https://api.x.ai/v1",
};

type OaiToolCall = { id: string; type: "function"; function: { name: string; arguments: string } };
type OaiMessage =
  | { role: "system" | "user"; content: string }
  | { role: "assistant"; content: string | null; tool_calls?: OaiToolCall[] }
  | { role: "tool"; tool_call_id: string; content: string };

async function runOpenAICompatible(route: Route, system: string, history: ChatTurn[], tools: ToolSpec[], run: ToolRunner) {
  const base = BASE_URL[route.provider as keyof typeof BASE_URL];
  const messages: OaiMessage[] = [{ role: "system", content: system }, ...history];
  const oaiTools = tools.map((t) => ({
    type: "function" as const,
    function: { name: t.name, description: t.description, parameters: t.input_schema },
  }));
  const result: LoopResult = { text: "", model: route.model, inputTokens: 0, outputTokens: 0, toolCalls: [] };

  for (let step = 0; step < MAX_STEPS; step++) {
    const res = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${route.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ ...modelFields(route), max_tokens: MAX_TOKENS, messages, tools: oaiTools }),
    });
    if (!res.ok) {
      const detail = (await res.text()).slice(0, 300);
      if (res.status === 403 && /Terms Of Service/i.test(detail)) {
        throw new GatewayError(
          `The AI provider refused this request for the account's region (${route.provider}, models ${route.model}). ` +
            "Add your own AI key under Settings → AI model keys, or change GENIE_OPENROUTER_MODEL.",
        );
      }
      throw new GatewayError(`${route.provider} returned ${res.status}: ${detail}`);
    }
    const body = (await res.json()) as {
      model?: string;
      usage?: { prompt_tokens?: number; completion_tokens?: number };
      choices: { finish_reason: string; message: { content: string | null; tool_calls?: OaiToolCall[] } }[];
    };
    result.model = body.model ?? route.model;
    result.inputTokens += body.usage?.prompt_tokens ?? 0;
    result.outputTokens += body.usage?.completion_tokens ?? 0;

    const msg = body.choices[0]?.message;
    if (!msg) throw new GatewayError(`${route.provider} returned no choices`);
    const calls = msg.tool_calls ?? [];
    if (calls.length === 0) {
      result.text = (msg.content ?? "").trim();
      return result;
    }
    messages.push({ role: "assistant", content: msg.content, tool_calls: calls });
    for (const call of calls) {
      result.toolCalls.push(call.function.name);
      let content: string;
      try {
        const input = call.function.arguments ? JSON.parse(call.function.arguments) : {};
        content = JSON.stringify(await run(call.function.name, input));
      } catch (e) {
        content = `Error: ${errorText(e)}`;
      }
      messages.push({ role: "tool", tool_call_id: call.id, content });
    }
  }
  result.stopped = "max_steps";
  result.text = "I couldn't finish within the step limit. Try a narrower question.";
  return result;
}

// OpenRouter: a fallback list (`models`) and only hosts that don't store or train on prompts — the
// prompts carry customer records read live, which Genie itself never stores either.
function modelFields(route: Route) {
  if (route.provider !== "openrouter") return { model: route.model };
  const models = route.model.split(",").map((m) => m.trim()).filter(Boolean);
  return { model: models[0], models, provider: { data_collection: "deny" } };
}

function errorText(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}
