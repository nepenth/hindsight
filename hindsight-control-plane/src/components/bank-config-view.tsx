"use client";

import { useState, useEffect } from "react";
import { useBank } from "@/lib/bank-context";
import { client } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Loader2, AlertCircle, Pencil, RotateCcw, MoreVertical } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// ─── Field metadata ───────────────────────────────────────────────────────────
// source: "profile"  → read/written via getBankProfile / updateBankProfile
// source: "config"   → default, read/written via getBankConfig / updateBankConfig
// showWhen: { field, value } → only shown when config[field] === value

interface FieldMeta {
  label: string;
  type: "number" | "select" | "textarea" | "boolean" | "trait";
  source?: "profile" | "config";
  description?: string;
  placeholder?: string;
  rows?: number;
  min?: number;
  max?: number;
  options?: string[];
  lowLabel?: string;
  highLabel?: string;
  showWhen?: { field: string; value: string };
}

interface CategoryMeta {
  title: string;
  description: string;
  fields: Record<string, FieldMeta>;
}

const FIELD_CATEGORIES: Record<string, CategoryMeta> = {
  retention: {
    title: "Retain",
    description: "Control what gets extracted and stored from content",
    fields: {
      retain_chunk_size: {
        label: "Chunk Size",
        type: "number",
        description: "Size of text chunks for processing (characters)",
        min: 500,
        max: 8000,
      },
      retain_extraction_mode: {
        label: "Extraction Mode",
        type: "select",
        description:
          "How aggressively to extract facts: concise (default, selective), verbose (capture everything), custom (write your own extraction rules)",
        options: ["concise", "verbose", "custom"],
      },
      retain_spec: {
        label: "Focus",
        type: "textarea",
        description:
          "What this bank should pay attention to. Steers the extraction without replacing it — works with any extraction mode.",
        placeholder:
          "Focus on technical decisions, architecture choices, and team member expertise. Ignore social conversation.",
        rows: 3,
      },
      retain_custom_instructions: {
        label: "Custom Extraction Prompt",
        type: "textarea",
        description:
          "Replaces the built-in extraction rules entirely. Only active when Extraction Mode is set to custom.",
        placeholder:
          "ONLY extract facts that are:\n✅ Technical decisions and rationale\n✅ Architecture and design choices\n\nDO NOT extract:\n❌ Greetings or social conversation",
        rows: 5,
        showWhen: { field: "retain_extraction_mode", value: "custom" },
      },
    },
  },
  consolidation: {
    title: "Observations",
    description: "Control how facts are synthesized into durable observations",
    fields: {
      enable_observations: {
        label: "Enable Observations",
        type: "boolean",
        description: "Enable automatic consolidation of facts into observations",
      },
      observations_spec: {
        label: "Observations Definition",
        type: "textarea",
        description:
          "What observations are for this bank. Replaces the built-in durable-knowledge rules — leave blank to use the default.",
        placeholder:
          "Observations are weekly summaries of sprint outcomes, blockers encountered, and team dynamics...",
        rows: 3,
      },
    },
  },
  reflect: {
    title: "Reflect",
    description: "Shape how the bank reasons and responds in reflect operations",
    fields: {
      mission: {
        label: "Mission",
        type: "textarea",
        source: "profile",
        description:
          "Agent identity and purpose. Used as framing context in reflect — not injected into retain or observations.",
        placeholder:
          "You are a meticulous engineering assistant. Always ground answers in the team's actual decisions and rationale.",
        rows: 3,
      },
      "disposition.skepticism": {
        label: "Skepticism",
        type: "trait",
        source: "profile",
        description: "How skeptical vs trusting when evaluating claims",
        lowLabel: "Trusting",
        highLabel: "Skeptical",
      },
      "disposition.literalism": {
        label: "Literalism",
        type: "trait",
        source: "profile",
        description: "How literally to interpret information",
        lowLabel: "Flexible",
        highLabel: "Literal",
      },
      "disposition.empathy": {
        label: "Empathy",
        type: "trait",
        source: "profile",
        description: "How much to weight emotional context",
        lowLabel: "Detached",
        highLabel: "Empathetic",
      },
    },
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

interface ProfileData {
  mission: string;
  disposition: { skepticism: number; literalism: number; empathy: number };
}

function getProfileValue(profile: ProfileData | null, fieldKey: string): any {
  if (!profile) return undefined;
  if (fieldKey === "mission") return profile.mission;
  if (fieldKey.startsWith("disposition.")) {
    const trait = fieldKey.split(".")[1] as keyof ProfileData["disposition"];
    return profile.disposition?.[trait];
  }
  return undefined;
}

// ─── BankConfigView ───────────────────────────────────────────────────────────

export function BankConfigView() {
  const { currentBank: bankId } = useBank();
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<Record<string, any>>({});
  const [overrides, setOverrides] = useState<Record<string, any>>({});
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    if (bankId) loadAll();
  }, [bankId]);

  const loadAll = async () => {
    if (!bankId) return;
    setLoading(true);
    try {
      const [configResp, profileResp] = await Promise.all([
        client.getBankConfig(bankId),
        client.getBankProfile(bankId),
      ]);
      setConfig(configResp.config);
      setOverrides(configResp.overrides);
      setProfile({ mission: profileResp.mission ?? "", disposition: profileResp.disposition });
    } catch (err) {
      console.error("Failed to load bank data:", err);
    } finally {
      setLoading(false);
    }
  };

  const confirmReset = async () => {
    if (!bankId) return;
    setResetting(true);
    try {
      await client.resetBankConfig(bankId);
      await loadAll();
      setShowResetDialog(false);
    } catch {
      // Error toast shown by API client interceptor
    } finally {
      setResetting(false);
    }
  };

  const getValue = (fieldKey: string, fieldMeta: FieldMeta) =>
    fieldMeta.source === "profile" ? getProfileValue(profile, fieldKey) : config[fieldKey];

  const renderReadOnlyField = (fieldKey: string, fieldMeta: FieldMeta) => {
    if (fieldMeta.showWhen && config[fieldMeta.showWhen.field] !== fieldMeta.showWhen.value) {
      return null;
    }
    const value = getValue(fieldKey, fieldMeta);

    return (
      <div
        key={fieldKey}
        className="flex items-start justify-between gap-4 p-3 border border-border rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium">{fieldMeta.label}</div>
          {fieldMeta.description && (
            <p className="text-xs text-muted-foreground mt-0.5">{fieldMeta.description}</p>
          )}
        </div>
        <div className="text-sm flex-shrink-0">
          {fieldMeta.type === "trait" ? (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground w-12 text-right">
                {fieldMeta.lowLabel}
              </span>
              <div className="flex gap-0.5">
                {[1, 2, 3, 4, 5].map((n) => (
                  <div
                    key={n}
                    className={`w-3 h-3 rounded-full ${n <= (value ?? 3) ? "bg-primary" : "bg-muted"}`}
                  />
                ))}
              </div>
              <span className="text-xs text-muted-foreground w-12">{fieldMeta.highLabel}</span>
              <span className="text-xs font-mono text-muted-foreground ml-1">{value ?? 3}/5</span>
            </div>
          ) : fieldMeta.type === "boolean" ? (
            <span className={value ? "text-green-600" : "text-muted-foreground"}>
              {value ? "Enabled" : "Disabled"}
            </span>
          ) : fieldMeta.type === "textarea" ? (
            <span className="text-muted-foreground italic font-mono text-xs max-w-48 truncate block">
              {value ? `${value.substring(0, 60)}${value.length > 60 ? "…" : ""}` : "Not set"}
            </span>
          ) : (
            <span className="font-mono">
              {value ?? <span className="text-muted-foreground italic">Not set</span>}
            </span>
          )}
        </div>
      </div>
    );
  };

  if (!bankId) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">No bank selected</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <>
      <div className="space-y-4">
        {/* Per-category cards */}
        {Object.entries(FIELD_CATEGORIES).map(([catKey, category]) => (
          <Card key={catKey}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base">{category.title}</CardTitle>
                  <CardDescription className="text-xs">{category.description}</CardDescription>
                </div>
                {/* Only show the edit/reset menu on the first card to avoid clutter */}
                {catKey === Object.keys(FIELD_CATEGORIES)[0] && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm" disabled={resetting}>
                        {resetting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <MoreVertical className="h-4 w-4" />
                        )}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setShowEditDialog(true)}>
                        <Pencil className="h-4 w-4 mr-2" />
                        Edit All
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setShowResetDialog(true)}>
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Reset to Defaults
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
                {catKey !== Object.keys(FIELD_CATEGORIES)[0] && (
                  <Button variant="ghost" size="sm" onClick={() => setShowEditDialog(true)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-2">
                {Object.entries(category.fields).map(([fieldKey, fieldMeta]) =>
                  renderReadOnlyField(fieldKey, fieldMeta)
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {showEditDialog && (
        <ConfigEditDialog
          bankId={bankId}
          initialConfig={config}
          overrides={overrides}
          initialProfile={profile}
          onClose={() => setShowEditDialog(false)}
          onSaved={() => {
            loadAll();
            setShowEditDialog(false);
          }}
        />
      )}

      <AlertDialog open={showResetDialog} onOpenChange={setShowResetDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset Configuration</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to reset all configuration overrides to defaults? This action
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resetting}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmReset} disabled={resetting}>
              {resetting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Resetting...
                </>
              ) : (
                "Reset to Defaults"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// ─── Edit dialog ──────────────────────────────────────────────────────────────

function ConfigEditDialog({
  bankId,
  initialConfig,
  overrides,
  initialProfile,
  onClose,
  onSaved,
}: {
  bankId: string;
  initialConfig: Record<string, any>;
  overrides: Record<string, any>;
  initialProfile: ProfileData | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState(initialConfig);
  const [editProfile, setEditProfile] = useState<ProfileData>(
    initialProfile ?? {
      mission: "",
      disposition: { skepticism: 3, literalism: 3, empathy: 3 },
    }
  );

  const handleConfigChange = (field: string, value: any) =>
    setConfig((prev) => ({ ...prev, [field]: value }));

  const handleProfileChange = (fieldKey: string, value: any) => {
    if (fieldKey === "mission") {
      setEditProfile((prev) => ({ ...prev, mission: value ?? "" }));
    } else if (fieldKey.startsWith("disposition.")) {
      const trait = fieldKey.split(".")[1] as keyof ProfileData["disposition"];
      setEditProfile((prev) => ({
        ...prev,
        disposition: { ...prev.disposition, [trait]: value },
      }));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const configUpdates: Record<string, any> = {};
      Object.keys(config).forEach((key) => {
        const fieldMeta = Object.values(FIELD_CATEGORIES)
          .flatMap((cat) => Object.entries(cat.fields))
          .find(([k]) => k === key)?.[1];
        if (fieldMeta && fieldMeta.source !== "profile") {
          configUpdates[key] = config[key];
        }
      });
      await client.updateBankConfig(bankId, configUpdates);
      await client.updateBankProfile(bankId, {
        mission: editProfile.mission,
        disposition: editProfile.disposition,
      });
      onSaved();
    } catch (err: any) {
      console.error("Failed to save:", err);
      setError(err.message || "Failed to save configuration");
      setSaving(false);
    }
  };

  const renderField = (fieldKey: string, fieldMeta: FieldMeta) => {
    if (fieldMeta.showWhen && config[fieldMeta.showWhen.field] !== fieldMeta.showWhen.value) {
      return null;
    }

    const isProfile = fieldMeta.source === "profile";
    const value = isProfile ? getProfileValue(editProfile, fieldKey) : config[fieldKey];
    const onChange = isProfile ? handleProfileChange : handleConfigChange;

    if (fieldMeta.type === "trait") {
      const traitValue = (value as number) ?? 3;
      return (
        <div key={fieldKey} className="space-y-2">
          <Label className="font-medium">{fieldMeta.label}</Label>
          {fieldMeta.description && (
            <p className="text-xs text-muted-foreground">{fieldMeta.description}</p>
          )}
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground w-14 text-right">
              {fieldMeta.lowLabel}
            </span>
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => onChange(fieldKey, n)}
                  className={`w-8 h-8 rounded-full text-xs font-semibold border transition-colors ${
                    n === traitValue
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-muted text-muted-foreground border-border hover:border-primary/50"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground w-14">{fieldMeta.highLabel}</span>
          </div>
        </div>
      );
    }

    if (fieldMeta.type === "boolean") {
      return (
        <div key={fieldKey} className="space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <Label className="font-medium">{fieldMeta.label}</Label>
              {fieldMeta.description && (
                <p className="text-xs text-muted-foreground mt-1">{fieldMeta.description}</p>
              )}
            </div>
            <button
              onClick={() => onChange(fieldKey, !value)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                value ? "bg-primary" : "bg-muted"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  value ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </div>
      );
    }

    if (fieldMeta.type === "select") {
      return (
        <div key={fieldKey} className="space-y-2">
          <Label className="font-medium">{fieldMeta.label}</Label>
          {fieldMeta.description && (
            <p className="text-xs text-muted-foreground">{fieldMeta.description}</p>
          )}
          <Select value={value?.toString()} onValueChange={(val) => onChange(fieldKey, val)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {fieldMeta.options!.map((opt) => (
                <SelectItem key={opt} value={opt}>
                  {opt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      );
    }

    if (fieldMeta.type === "textarea") {
      return (
        <div key={fieldKey} className="space-y-2">
          <Label className="font-medium">{fieldMeta.label}</Label>
          {fieldMeta.description && (
            <p className="text-xs text-muted-foreground">{fieldMeta.description}</p>
          )}
          <Textarea
            id={fieldKey}
            value={value || ""}
            onChange={(e) => onChange(fieldKey, e.target.value || null)}
            placeholder={fieldMeta.placeholder}
            rows={fieldMeta.rows || 3}
            className="font-mono text-sm"
          />
        </div>
      );
    }

    return (
      <div key={fieldKey} className="space-y-2">
        <Label className="font-medium">{fieldMeta.label}</Label>
        {fieldMeta.description && (
          <p className="text-xs text-muted-foreground">{fieldMeta.description}</p>
        )}
        <Input
          id={fieldKey}
          type={fieldMeta.type || "text"}
          value={value ?? ""}
          onChange={(e) =>
            onChange(
              fieldKey,
              fieldMeta.type === "number" ? parseFloat(e.target.value) : e.target.value
            )
          }
          min={fieldMeta.min}
          max={fieldMeta.max}
        />
      </div>
    );
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Configuration</DialogTitle>
          <DialogDescription>
            Customize behavioral settings for this bank. Changes only affect this bank and override
            global defaults.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-8 py-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {Object.entries(FIELD_CATEGORIES).map(([catKey, category]) => (
            <div key={catKey} className="space-y-4">
              <div className="border-b border-border pb-1">
                <h3 className="text-sm font-semibold">{category.title}</h3>
                <p className="text-xs text-muted-foreground">{category.description}</p>
              </div>
              <div className="grid gap-4">
                {Object.entries(category.fields).map(([fieldKey, fieldMeta]) =>
                  renderField(fieldKey, fieldMeta)
                )}
              </div>
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button onClick={onClose} variant="outline" disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
