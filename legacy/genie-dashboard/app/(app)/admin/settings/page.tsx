"use client";

import { useEffect, useState } from "react";
import { AdminConfig, getAdminConfig, updateAdminConfig } from "@/lib/api";

const inputCls =
  "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";

export default function SettingsPage() {
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // General settings
  const [inboxFolder, setInboxFolder] = useState("");
  const [processedFolder, setProcessedFolder] = useState("");
  const [moveWhenDone, setMoveWhenDone] = useState(false);
  const [timerEnabled, setTimerEnabled] = useState(true);

  // OneDrive credentials
  const [msClientId, setMsClientId] = useState("");
  const [msTenantId, setMsTenantId] = useState("");
  const [msClientSecret, setMsClientSecret] = useState("");
  const [msDriveId, setMsDriveId] = useState("");

  useEffect(() => {
    getAdminConfig()
      .then((cfg) => {
        setConfig(cfg);
        setInboxFolder(cfg.inbox_folder);
        setProcessedFolder(cfg.processed_folder ?? "/Document Processor/Processed");
        setMoveWhenDone(cfg.move_when_done);
        setTimerEnabled(cfg.timer_enabled ?? true);
        setMsClientId(cfg.ms_client_id ?? "");
        setMsTenantId(cfg.ms_tenant_id ?? "");
        setMsDriveId(cfg.ms_drive_id ?? "");
        // ms_client_secret is write-only — never pre-filled
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const payload: Parameters<typeof updateAdminConfig>[0] = {
        inbox_folder: inboxFolder.trim(),
        processed_folder: processedFolder.trim(),
        move_when_done: moveWhenDone,
        timer_enabled: timerEnabled,
        ms_client_id: msClientId.trim(),
        ms_tenant_id: msTenantId.trim(),
        ms_drive_id: msDriveId.trim(),
      };
      // Only send secret if the user typed something
      if (msClientSecret.trim()) payload.ms_client_secret = msClientSecret.trim();

      const updated = await updateAdminConfig(payload);
      setConfig(updated);
      setMsClientSecret(""); // clear after save
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    if (!config) return;
    setInboxFolder(config.inbox_folder);
    setProcessedFolder(config.processed_folder ?? "/Document Processor/Processed");
    setMoveWhenDone(config.move_when_done);
    setTimerEnabled(config.timer_enabled ?? true);
    setMsClientId(config.ms_client_id ?? "");
    setMsTenantId(config.ms_tenant_id ?? "");
    setMsDriveId(config.ms_drive_id ?? "");
    setMsClientSecret("");
    setError(null);
  }

  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Settings</h1>
      <p className="text-sm text-gray-500 mb-6">Runtime configuration stored in Azure Blob Storage.</p>

      {loading && <p className="text-sm text-gray-500">Loading…</p>}

      {!loading && (
        <form onSubmit={handleSave} className="space-y-8">

          {/* ── General ──────────────────────────────────────────────────── */}
          <section className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                OneDrive Inbox Folder
              </label>
              <input
                type="text"
                value={inboxFolder}
                onChange={(e) => setInboxFolder(e.target.value)}
                placeholder="/Document Processor/In"
                className={inputCls}
              />
              <p className="mt-1 text-xs text-gray-400">
                OneDrive path that the timer trigger reads for new files.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                OneDrive Processed Folder
              </label>
              <input
                type="text"
                value={processedFolder}
                onChange={(e) => setProcessedFolder(e.target.value)}
                placeholder="/Document Processor/Processed"
                className={inputCls}
              />
              <p className="mt-1 text-xs text-gray-400">
                Default destination shown in the Ingest page after processing a file.
              </p>
            </div>

            <div className="flex items-start gap-3">
              <div className="flex h-5 items-center">
                <input
                  id="timer_enabled"
                  type="checkbox"
                  checked={timerEnabled}
                  onChange={(e) => setTimerEnabled(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
              </div>
              <div>
                <label htmlFor="timer_enabled" className="text-sm font-medium text-gray-700">
                  Auto-process OneDrive inbox every 5 minutes
                  {timerEnabled ? (
                    <span className="ml-2 text-xs font-normal text-green-600">● running</span>
                  ) : (
                    <span className="ml-2 text-xs font-normal text-gray-400">○ paused</span>
                  )}
                </label>
                <p className="text-xs text-gray-400 mt-0.5">
                  When enabled, the background timer picks up and processes files dropped in the OneDrive inbox.
                  Disable if you process all files manually via the Ingest page.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="flex h-5 items-center">
                <input
                  id="move_when_done"
                  type="checkbox"
                  checked={moveWhenDone}
                  onChange={(e) => setMoveWhenDone(e.target.checked)}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
              </div>
              <div>
                <label htmlFor="move_when_done" className="text-sm font-medium text-gray-700">
                  Move files to /Processed after processing
                </label>
                <p className="text-xs text-gray-400 mt-0.5">
                  When enabled, successfully processed files are moved from /In to /Processed.
                  Disable to keep files in /In (useful during testing).
                </p>
              </div>
            </div>
          </section>

          {/* ── OneDrive Credentials ─────────────────────────────────────── */}
          <section className="space-y-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-800">OneDrive Credentials</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                Microsoft Graph API credentials for OneDrive access. Environment variables
                take priority if set on the server.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Client ID
              </label>
              <input
                type="text"
                value={msClientId}
                onChange={(e) => setMsClientId(e.target.value)}
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                className={inputCls}
                autoComplete="off"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Tenant ID
              </label>
              <input
                type="text"
                value={msTenantId}
                onChange={(e) => setMsTenantId(e.target.value)}
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                className={inputCls}
                autoComplete="off"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Client Secret
                {config?.ms_client_secret_configured && (
                  <span className="ml-2 text-green-600 font-normal">● configured</span>
                )}
              </label>
              <input
                type="password"
                value={msClientSecret}
                onChange={(e) => setMsClientSecret(e.target.value)}
                placeholder={
                  config?.ms_client_secret_configured
                    ? "Leave blank to keep existing secret"
                    : "Enter client secret"
                }
                className={inputCls}
                autoComplete="new-password"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Drive ID
              </label>
              <input
                type="text"
                value={msDriveId}
                onChange={(e) => setMsDriveId(e.target.value)}
                placeholder="b!xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                className={inputCls}
                autoComplete="off"
              />
              <p className="mt-1 text-xs text-gray-400">
                The OneDrive or SharePoint document library drive ID.
              </p>
            </div>
          </section>

          {/* ── Status / Actions ─────────────────────────────────────────── */}
          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          {saved && (
            <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              Settings saved successfully.
            </p>
          )}

          <div className="flex items-center gap-3 pt-1">
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? "Saving…" : "Save Settings"}
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              Reset
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
