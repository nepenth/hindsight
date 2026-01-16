"use client";

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { client } from "@/lib/api";
import { useBank } from "@/lib/bank-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  RefreshCw,
  Lightbulb,
  Sparkles,
  Target,
  Pencil,
  Check,
  X,
  Plus,
  Pin,
  ChevronDown,
  FileText,
  Calendar,
  Tag,
  Users,
  ChevronRight,
  Loader2,
  ExternalLink,
  AlertTriangle,
  Trash2,
} from "lucide-react";
import { MemoryDetailModal } from "./memory-detail-modal";

type ViewMode = "dashboard" | "table";

interface ObservationEvidence {
  memory_id: string;
  quote: string;
  relevance: string;
  timestamp: string;
}

interface MentalModelObservation {
  title: string;
  // 'content' is used for generated observations, 'text' for directives
  content?: string;
  text?: string;
  evidence?: ObservationEvidence[];
  based_on?: string[]; // For directives
  created_at?: string;
  trend?: "stable" | "strengthening" | "weakening" | "new" | "stale";
  evidence_count?: number;
  evidence_span?: { from: string | null; to: string | null };
}

interface MentalModelFreshness {
  is_up_to_date: boolean;
  last_refresh_at: string | null;
  memories_since_refresh: number;
}

interface MentalModel {
  id: string;
  bank_id: string;
  subtype: string;
  name: string;
  description: string;
  observations?: MentalModelObservation[];
  entity_id: string | null;
  links: string[];
  tags?: string[];
  last_updated: string | null;
  last_refresh_at: string | null;
  freshness?: MentalModelFreshness | null;
  created_at: string;
}

// Helper to count total source memories across all observations
function getTotalMemoryCount(model: MentalModel): number {
  return model.observations?.reduce((sum, obs) => sum + (obs.evidence?.length || 0), 0) || 0;
}

export function MentalModelsView() {
  const { currentBank } = useBank();
  const [mentalModels, setMentalModels] = useState<MentalModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState<
    "all" | "pinned" | "structural" | "emergent" | "learned" | null
  >(null);
  const [operationStatus, setOperationStatus] = useState<{
    operationId: string;
    type: "all" | "pinned" | "structural" | "emergent" | "learned";
    status: "pending" | "completed" | "failed" | "not_found";
    errorMessage?: string | null;
  } | null>(null);
  const [mission, setMission] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("dashboard");
  const [selectedModel, setSelectedModel] = useState<MentalModel | null>(null);

  // Mission editing state
  const [editingMission, setEditingMission] = useState(false);
  const [editMissionValue, setEditMissionValue] = useState("");
  const [savingMission, setSavingMission] = useState(false);

  // Create mental model state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createType, setCreateType] = useState<"pinned" | "directive">("pinned");
  const [creating, setCreating] = useState(false);
  const [newModel, setNewModel] = useState({ name: "", description: "" });

  // Delete state
  const [deletingModel, setDeletingModel] = useState<string | null>(null);

  // Auto-refresh interval (5 seconds)
  const AUTO_REFRESH_INTERVAL = 5000;
  const currentBankRef = useRef(currentBank);
  currentBankRef.current = currentBank;
  const selectedModelRef = useRef(selectedModel);
  selectedModelRef.current = selectedModel;

  const loadMentalModels = async () => {
    if (!currentBank) return;

    setLoading(true);
    try {
      const [modelsData, profileData] = await Promise.all([
        client.listMentalModels(currentBank),
        client.getBankProfile(currentBank),
      ]);
      setMentalModels(modelsData.items || []);
      setMission(profileData.mission);
      setEditMissionValue(profileData.mission || "");
    } catch (error) {
      console.error("Error loading mental models:", error);
    } finally {
      setLoading(false);
    }
  };

  // Silent refresh for auto-refresh (no loading spinner)
  const silentRefreshModels = async () => {
    const bank = currentBankRef.current;
    if (!bank) return;

    try {
      const modelsData = await client.listMentalModels(bank);
      const items = modelsData.items || [];
      setMentalModels(items);

      // Update selected model if it exists in the refreshed list
      const currentSelected = selectedModelRef.current;
      if (currentSelected) {
        const updatedModel = items.find((m) => m.id === currentSelected.id);
        if (updatedModel) {
          setSelectedModel(updatedModel);
        }
      }
    } catch (error) {
      console.error("Error auto-refreshing mental models:", error);
    }
  };

  const handleSaveMission = async () => {
    if (!currentBank) return;

    setSavingMission(true);
    try {
      await client.setBankMission(currentBank, editMissionValue);
      setMission(editMissionValue || null);
      setEditingMission(false);
    } catch (error) {
      console.error("Error saving mission:", error);
      alert("Error saving mission: " + (error as Error).message);
    } finally {
      setSavingMission(false);
    }
  };

  const handleCancelEditMission = () => {
    setEditMissionValue(mission || "");
    setEditingMission(false);
  };

  const handleRefresh = async (subtype?: "structural" | "emergent" | "pinned" | "learned") => {
    if (!currentBank) return;

    const refreshType = subtype || "all";
    setRefreshing(refreshType);
    setOperationStatus(null);
    try {
      const result = await client.refreshMentalModels(currentBank, subtype);
      // Start polling for operation status
      if (result.operation_id) {
        setOperationStatus({
          operationId: result.operation_id,
          type: refreshType,
          status: "pending",
        });
        pollOperationStatus(result.operation_id, refreshType);
      }
    } catch (error) {
      console.error("Error refreshing mental models:", error);
      alert("Error refreshing mental models: " + (error as Error).message);
    } finally {
      setRefreshing(null);
    }
  };

  const pollOperationStatus = async (
    operationId: string,
    type: "all" | "pinned" | "structural" | "emergent" | "learned"
  ) => {
    const bank = currentBankRef.current;
    if (!bank) return;

    const poll = async () => {
      try {
        const status = await client.getOperationStatus(bank, operationId);
        setOperationStatus({
          operationId,
          type,
          status: status.status,
          errorMessage: status.error_message,
        });

        if (status.status === "pending") {
          // Continue polling every 2 seconds
          setTimeout(poll, 2000);
        } else {
          // Operation completed or failed - refresh models and clear after delay
          if (status.status === "completed") {
            await silentRefreshModels();
          }
          setTimeout(() => setOperationStatus(null), 5000);
        }
      } catch (error) {
        console.error("Error polling operation status:", error);
        // On error, assume completed and clear
        setOperationStatus(null);
      }
    };

    poll();
  };

  const handleCreateModel = async () => {
    if (!currentBank || !newModel.name.trim() || !newModel.description.trim()) return;

    setCreating(true);
    try {
      await client.createMentalModel(currentBank, {
        name: newModel.name.trim(),
        description: newModel.description.trim(),
        subtype: createType === "directive" ? "directive" : undefined,
      });

      // Reset form and reload
      setNewModel({ name: "", description: "" });
      setCreateType("pinned");
      setShowCreateForm(false);
      await loadMentalModels();
    } catch (error) {
      console.error("Error creating mental model:", error);
      alert("Error creating mental model: " + (error as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    if (!currentBank) return;

    setDeletingModel(modelId);
    try {
      await client.deleteMentalModel(currentBank, modelId);
      await loadMentalModels();
      if (selectedModel?.id === modelId) {
        setSelectedModel(null);
      }
    } catch (error) {
      console.error("Error deleting mental model:", error);
      alert("Error deleting mental model: " + (error as Error).message);
    } finally {
      setDeletingModel(null);
    }
  };

  useEffect(() => {
    if (currentBank) {
      loadMentalModels();

      // Set up auto-refresh interval for mental models only
      const intervalId = setInterval(silentRefreshModels, AUTO_REFRESH_INTERVAL);

      return () => {
        clearInterval(intervalId);
      };
    }
  }, [currentBank]);

  // Close detail panel on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedModel) {
        setSelectedModel(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedModel]);

  if (!currentBank) {
    return (
      <Card>
        <CardContent className="p-10 text-center">
          <p className="text-muted-foreground">Select a memory bank to view mental models.</p>
        </CardContent>
      </Card>
    );
  }

  // Group mental models by subtype
  const pinnedModels = mentalModels.filter((m) => m.subtype === "pinned");
  const structuralModels = mentalModels.filter((m) => m.subtype === "structural");
  const emergentModels = mentalModels.filter((m) => m.subtype === "emergent");
  const learnedModels = mentalModels.filter((m) => m.subtype === "learned");
  const directiveModels = mentalModels.filter((m) => m.subtype === "directive");

  const getSubtypeIcon = (subtype: string) => {
    switch (subtype) {
      case "pinned":
        return <Pin className="w-4 h-4 text-amber-500" />;
      case "structural":
        return <Target className="w-4 h-4 text-blue-500" />;
      case "emergent":
        return <Sparkles className="w-4 h-4 text-emerald-500" />;
      case "learned":
        return <Lightbulb className="w-4 h-4 text-violet-500" />;
      case "directive":
        return <AlertTriangle className="w-4 h-4 text-rose-500" />;
      default:
        return <Lightbulb className="w-4 h-4 text-slate-500" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Mission section - compact inline style */}
      <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-muted/50 border border-border">
        <Target className="w-4 h-4 text-muted-foreground shrink-0" />
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide shrink-0">
          Mission:
        </span>
        {editingMission ? (
          <div className="flex gap-2 items-center flex-1">
            <Input
              value={editMissionValue}
              onChange={(e) => setEditMissionValue(e.target.value)}
              placeholder="e.g., Be a PM for the engineering team..."
              className="flex-1 h-7 text-sm"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveMission();
                if (e.key === "Escape") handleCancelEditMission();
              }}
            />
            <Button
              size="icon"
              variant="ghost"
              onClick={handleSaveMission}
              disabled={savingMission}
              className="h-7 w-7"
              title="Save mission"
            >
              <Check className="w-3.5 h-3.5 text-green-600" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              onClick={handleCancelEditMission}
              disabled={savingMission}
              className="h-7 w-7"
              title="Cancel"
            >
              <X className="w-3.5 h-3.5 text-red-600" />
            </Button>
          </div>
        ) : (
          <>
            <span
              className={`text-sm flex-1 ${mission ? "text-foreground" : "text-muted-foreground italic"}`}
            >
              {mission || "No mission set"}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditingMission(true)}
              className="h-6 px-2 text-xs"
            >
              <Pencil className="w-3 h-3 mr-1" />
              {mission ? "Edit" : "Set"}
            </Button>
          </>
        )}
      </div>

      {/* Header with count, actions, and view toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <p className="text-sm text-muted-foreground">
            {mentalModels.length} mental model{mentalModels.length !== 1 ? "s" : ""}
          </p>
          <div className="flex gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  size="sm"
                  disabled={!!refreshing || !mission}
                  title={
                    !mission
                      ? "Set a mission first to refresh mental models"
                      : "Refresh mental models"
                  }
                  className="h-8"
                >
                  {refreshing ? (
                    <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4 mr-1" />
                  )}
                  {refreshing ? "Refreshing..." : "Refresh"}
                  <ChevronDown className="w-3 h-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => handleRefresh()}>
                  <Sparkles className="w-4 h-4" />
                  All
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleRefresh("pinned")}>
                  <Pin className="w-4 h-4 text-amber-500" />
                  Pinned
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleRefresh("structural")}>
                  <Target className="w-4 h-4 text-blue-500" />
                  Structural
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleRefresh("emergent")}>
                  <Sparkles className="w-4 h-4 text-emerald-500" />
                  Emergent
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleRefresh("learned")}>
                  <Lightbulb className="w-4 h-4 text-violet-500" />
                  Learned
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* View mode toggle - top right like data-view */}
        <div className="flex items-center gap-2 bg-muted rounded-lg p-1">
          <button
            onClick={() => setViewMode("dashboard")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              viewMode === "dashboard"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Dashboard
          </button>
          <button
            onClick={() => setViewMode("table")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              viewMode === "table"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Table
          </button>
        </div>
      </div>

      {/* Regeneration Progress Banner */}
      {refreshing && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-primary/10 border border-primary/20 animate-in fade-in duration-300">
          <RefreshCw className="w-4 h-4 text-primary animate-spin" />
          <span className="text-sm font-medium text-foreground">
            Scheduling regeneration for{" "}
            {refreshing === "all" ? "all mental models" : `${refreshing} models`}...
          </span>
        </div>
      )}

      {/* Operation Status Banner - shows operation progress */}
      {operationStatus && !refreshing && (
        <div
          className={`flex items-center gap-3 px-4 py-3 rounded-lg animate-in fade-in duration-300 ${
            operationStatus.status === "pending"
              ? "bg-blue-500/10 border border-blue-500/20"
              : operationStatus.status === "completed"
                ? "bg-emerald-500/10 border border-emerald-500/20"
                : "bg-rose-500/10 border border-rose-500/20"
          }`}
        >
          {operationStatus.status === "pending" ? (
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
          ) : operationStatus.status === "completed" ? (
            <Check className="w-4 h-4 text-emerald-500" />
          ) : (
            <X className="w-4 h-4 text-rose-500" />
          )}
          <span className="text-sm font-medium text-foreground">
            {operationStatus.status === "pending"
              ? `Refreshing ${operationStatus.type === "all" ? "all mental models" : `${operationStatus.type} models`}...`
              : operationStatus.status === "completed"
                ? `Successfully refreshed ${operationStatus.type === "all" ? "all mental models" : `${operationStatus.type} models`}`
                : `Failed to refresh ${operationStatus.type === "all" ? "all mental models" : `${operationStatus.type} models`}`}
          </span>
          {operationStatus.status === "pending" && (
            <span className="text-xs text-muted-foreground">Running in background...</span>
          )}
          {operationStatus.errorMessage && (
            <span className="text-xs text-rose-500">{operationStatus.errorMessage}</span>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto h-6 px-2 text-xs"
            onClick={() => setOperationStatus(null)}
          >
            <X className="w-3 h-3" />
          </Button>
        </div>
      )}

      {/* Create Mental Model Dialog */}
      <Dialog
        open={showCreateForm}
        onOpenChange={(open) => {
          setShowCreateForm(open);
          if (!open) {
            setNewModel({ name: "", description: "" });
            setCreateType("pinned");
          }
        }}
      >
        <DialogContent
          className={`sm:max-w-lg border-2 ${createType === "directive" ? "border-rose-500" : "border-primary"}`}
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {createType === "directive" ? (
                <>
                  <AlertTriangle className="w-5 h-5 text-rose-500" />
                  Create Directive
                </>
              ) : (
                <>
                  <Pin className="w-5 h-5 text-primary" />
                  Create Pinned Mental Model
                </>
              )}
            </DialogTitle>
            <DialogDescription>
              {createType === "directive"
                ? "Directives are hard rules that the agent MUST follow in all responses."
                : "Pinned models persist across regeneration and help organize your memory bank."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Type selector */}
            <div className="flex gap-2">
              <Button
                variant={createType === "pinned" ? "default" : "outline"}
                size="sm"
                onClick={() => setCreateType("pinned")}
                className="flex-1"
              >
                <Pin className="w-4 h-4 mr-1" />
                Pinned Model
              </Button>
              <Button
                variant={createType === "directive" ? "default" : "outline"}
                size="sm"
                onClick={() => setCreateType("directive")}
                className={`flex-1 ${createType === "directive" ? "bg-rose-500 hover:bg-rose-600" : ""}`}
              >
                <AlertTriangle className="w-4 h-4 mr-1" />
                Directive
              </Button>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Name *</label>
              <Input
                value={newModel.name}
                onChange={(e) => setNewModel({ ...newModel, name: e.target.value })}
                placeholder={
                  createType === "directive"
                    ? "e.g., Competitor Policy, Response Guidelines"
                    : "e.g., Product Roadmap, Team Structure, Q1 Goals"
                }
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                {createType === "directive" ? "Rule *" : "Description *"}
              </label>
              <Textarea
                value={newModel.description}
                onChange={(e) => setNewModel({ ...newModel, description: e.target.value })}
                placeholder={
                  createType === "directive"
                    ? "e.g., Never mention competitor products. When asked about competitors, redirect to our features instead."
                    : "What should this mental model track?"
                }
                className={createType === "directive" ? "min-h-[120px]" : "min-h-[60px]"}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowCreateForm(false);
                setNewModel({ name: "", description: "" });
                setCreateType("pinned");
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateModel}
              disabled={creating || !newModel.name.trim() || !newModel.description.trim()}
              className={createType === "directive" ? "bg-rose-500 hover:bg-rose-600" : ""}
            >
              {creating ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Loading state */}
      {loading ? (
        <div className="text-center py-12">
          <RefreshCw className="w-8 h-8 mx-auto mb-3 text-muted-foreground animate-spin" />
          <p className="text-muted-foreground">Loading mental models...</p>
        </div>
      ) : mentalModels.length > 0 ? (
        <>
          {/* Table View */}
          {viewMode === "table" && (
            <div className="border rounded-lg overflow-hidden">
              <Table className="table-fixed">
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead className="w-[28%]">Name</TableHead>
                    <TableHead className="w-[10%]">Source</TableHead>
                    <TableHead className="w-[32%]">Description</TableHead>
                    <TableHead className="w-[8%] text-center">Obs</TableHead>
                    <TableHead className="w-[10%] text-center">Memories</TableHead>
                    <TableHead className="w-[12%]">Updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mentalModels.map((model) => (
                    <TableRow
                      key={model.id}
                      onClick={() => setSelectedModel(model)}
                      className={`cursor-pointer hover:bg-muted/50 ${
                        selectedModel?.id === model.id ? "bg-primary/10" : ""
                      }`}
                    >
                      <TableCell className="py-2">
                        <div className="flex items-center gap-2">
                          {getSubtypeIcon(model.subtype)}
                          <span className="font-medium text-foreground truncate">{model.name}</span>
                        </div>
                      </TableCell>
                      <TableCell className="py-2">
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            model.subtype === "pinned"
                              ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                              : model.subtype === "structural"
                                ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                                : model.subtype === "learned"
                                  ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                                  : model.subtype === "directive"
                                    ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                                    : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                          }`}
                        >
                          {model.subtype}
                        </span>
                      </TableCell>
                      <TableCell className="py-2">
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {model.description}
                        </p>
                      </TableCell>
                      <TableCell className="py-2 text-center text-sm text-foreground">
                        {model.observations?.length || 0}
                      </TableCell>
                      <TableCell className="py-2 text-center text-sm text-foreground">
                        {getTotalMemoryCount(model)}
                      </TableCell>
                      <TableCell className="py-2 text-xs">
                        <div className="flex items-center gap-2">
                          {model.freshness && !model.freshness.is_up_to_date && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px]">
                              {model.freshness.memories_since_refresh} new
                            </span>
                          )}
                          <span className="text-muted-foreground">
                            {model.last_refresh_at
                              ? new Date(model.last_refresh_at).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                }) +
                                " " +
                                new Date(model.last_refresh_at).toLocaleTimeString("en-US", {
                                  hour: "numeric",
                                  minute: "2-digit",
                                })
                              : "-"}
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Dashboard View - Grouped by subtype, 2 columns */}
          {/* Order: Structural, Emergent, Pinned, Learned */}
          {viewMode === "dashboard" && (
            <div className="space-y-8">
              {/* Structural Models Section */}
              {structuralModels.length > 0 && (
                <div>
                  <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-blue-500" />
                    Structural Models
                    <span className="text-sm font-normal text-muted-foreground">
                      (Mission-derived)
                    </span>
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    {structuralModels.map((model) => (
                      <ModelListCard
                        key={model.id}
                        model={model}
                        selected={selectedModel?.id === model.id}
                        onClick={() => setSelectedModel(model)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Emergent Models Section - Always show */}
              <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-emerald-500" />
                  Emergent Models
                  <span className="text-sm font-normal text-muted-foreground">
                    (Pattern-derived)
                  </span>
                </h3>
                {emergentModels.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {emergentModels.map((model) => (
                      <ModelListCard
                        key={model.id}
                        model={model}
                        selected={selectedModel?.id === model.id}
                        onClick={() => setSelectedModel(model)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="p-6 border border-dashed border-border rounded-lg text-center">
                    <Sparkles className="w-6 h-6 mx-auto mb-2 text-emerald-500/50" />
                    <p className="text-sm text-muted-foreground">
                      No emergent models yet. Models are discovered from patterns in your data.
                    </p>
                  </div>
                )}
              </div>

              {/* Pinned Models Section - Always show */}
              <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-amber-500" />
                  Pinned Models
                  <span className="text-sm font-normal text-muted-foreground">(User-defined)</span>
                  <Button
                    onClick={() => {
                      setCreateType("pinned");
                      setShowCreateForm(true);
                    }}
                    variant="outline"
                    size="sm"
                    className="ml-auto h-7 text-xs"
                  >
                    <Plus className="w-3 h-3 mr-1" />
                    Add
                  </Button>
                </h3>
                {pinnedModels.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {pinnedModels.map((model) => (
                      <PinnedModelCard
                        key={model.id}
                        model={model}
                        selected={selectedModel?.id === model.id}
                        onClick={() => setSelectedModel(model)}
                        onDelete={() => handleDeleteModel(model.id)}
                        deleting={deletingModel === model.id}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="p-6 border border-dashed border-border rounded-lg text-center">
                    <Pin className="w-6 h-6 mx-auto mb-2 text-amber-500/50" />
                    <p className="text-sm text-muted-foreground">
                      No pinned models yet. Create custom models to track specific topics.
                    </p>
                  </div>
                )}
              </div>

              {/* Learned Models Section - Always show */}
              <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-violet-500" />
                  Learned Models
                  <span className="text-sm font-normal text-muted-foreground">
                    (Reflection-derived)
                  </span>
                </h3>
                {learnedModels.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {learnedModels.map((model) => (
                      <ModelListCard
                        key={model.id}
                        model={model}
                        selected={selectedModel?.id === model.id}
                        onClick={() => setSelectedModel(model)}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="p-6 border border-dashed border-border rounded-lg text-center">
                    <Lightbulb className="w-6 h-6 mx-auto mb-2 text-violet-500/50" />
                    <p className="text-sm text-muted-foreground">
                      No learned models yet. Models are created automatically during reflection.
                    </p>
                  </div>
                )}
              </div>

              {/* Directives Section - Always show */}
              <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-rose-500" />
                  Directives
                  <span className="text-sm font-normal text-muted-foreground">(Hard rules)</span>
                  <Button
                    onClick={() => {
                      setCreateType("directive");
                      setShowCreateForm(true);
                    }}
                    variant="outline"
                    size="sm"
                    className="ml-auto h-7 text-xs"
                  >
                    <Plus className="w-3 h-3 mr-1" />
                    Add
                  </Button>
                </h3>
                {directiveModels.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3">
                    {directiveModels.map((model) => (
                      <DirectiveCard
                        key={model.id}
                        model={model}
                        selected={selectedModel?.id === model.id}
                        onClick={() => setSelectedModel(model)}
                        onDelete={() => handleDeleteModel(model.id)}
                        deleting={deletingModel === model.id}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="p-6 border border-dashed border-rose-500/30 rounded-lg text-center">
                    <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-rose-500/50" />
                    <p className="text-sm text-muted-foreground">
                      No directives yet. Directives are hard rules that the agent must follow.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      ) : (
        <Card>
          <CardContent className="p-12 text-center">
            <Lightbulb className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <h3 className="text-lg font-medium mb-2">No Mental Models Yet</h3>
            <p className="text-muted-foreground text-sm max-w-md mx-auto">
              {!mission
                ? "Set a mission above, then use the refresh buttons to create mental models."
                : "Use the refresh buttons to create mental models. Click 'All' for both types, or refresh 'Structural' (from mission) and 'Emergent' (from data) separately."}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Detail Panel - Fixed on Right */}
      {selectedModel && (
        <div className="fixed right-0 top-0 h-screen w-1/2 bg-card border-l-2 border-primary shadow-2xl z-50 overflow-y-auto animate-in slide-in-from-right duration-300 ease-out">
          <MentalModelDetailPanel
            model={selectedModel}
            onClose={() => setSelectedModel(null)}
            onRegenerated={silentRefreshModels}
          />
        </div>
      )}
    </div>
  );
}

// Compact card for dashboard view (no subtype chip since already grouped)
function ModelListCard({
  model,
  selected,
  onClick,
}: {
  model: MentalModel;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <Card
      className={`cursor-pointer transition-colors ${
        selected ? "bg-primary/10 border-primary" : "hover:bg-muted/50"
      }`}
      onClick={onClick}
    >
      <CardContent className="p-3">
        <div className="flex-1 min-w-0">
          <span className="font-medium text-sm text-foreground">{model.name}</span>
          <p className="text-xs text-muted-foreground line-clamp-2 mt-1">{model.description}</p>
          <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
            <span>
              <span className="font-medium text-foreground">{model.observations?.length || 0}</span>{" "}
              obs
            </span>
            <span>
              <span className="font-medium text-foreground">{getTotalMemoryCount(model)}</span>{" "}
              memories
            </span>
            {model.freshness && !model.freshness.is_up_to_date && (
              <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
                {model.freshness.memories_since_refresh} new
              </span>
            )}
            {model.last_refresh_at && (
              <span>
                {new Date(model.last_refresh_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </span>
            )}
          </div>
          {model.tags && model.tags.length > 0 && (
            <div className="flex items-center gap-1 mt-2 flex-wrap">
              <Tag className="w-3 h-3 text-muted-foreground" />
              {model.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// Card for pinned models with delete button
function PinnedModelCard({
  model,
  selected,
  onClick,
  onDelete,
  deleting,
}: {
  model: MentalModel;
  selected: boolean;
  onClick: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <Card
      className={`cursor-pointer transition-colors ${
        selected ? "bg-primary/10 border-primary" : "hover:bg-muted/50"
      }`}
      onClick={onClick}
    >
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Pin className="w-4 h-4 text-amber-500 shrink-0" />
              <span className="font-medium text-sm text-foreground">{model.name}</span>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-2 mt-1">{model.description}</p>
            <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
              <span>
                <span className="font-medium text-foreground">
                  {model.observations?.length || 0}
                </span>{" "}
                obs
              </span>
              <span>
                <span className="font-medium text-foreground">{getTotalMemoryCount(model)}</span>{" "}
                memories
              </span>
              {model.freshness && !model.freshness.is_up_to_date && (
                <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
                  {model.freshness.memories_since_refresh} new
                </span>
              )}
              {model.last_refresh_at && (
                <span>
                  {new Date(model.last_refresh_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })}
                </span>
              )}
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            disabled={deleting}
          >
            {deleting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// Card for directives with delete button
function DirectiveCard({
  model,
  selected,
  onClick,
  onDelete,
  deleting,
}: {
  model: MentalModel;
  selected: boolean;
  onClick: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <Card
      className={`cursor-pointer transition-colors border-rose-500/30 ${
        selected ? "bg-rose-500/10 border-rose-500" : "hover:bg-rose-500/5"
      }`}
      onClick={onClick}
    >
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
              <span className="font-medium text-sm text-foreground">{model.name}</span>
            </div>
            <p className="text-xs text-muted-foreground line-clamp-3 mt-1">{model.description}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 shrink-0"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            disabled={deleting}
          >
            {deleting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// Detail panel for mental model (like MemoryDetailPanel)
function MentalModelDetailPanel({
  model,
  onClose,
  onRegenerated,
}: {
  model: MentalModel;
  onClose: () => void;
  onRegenerated?: () => void;
}) {
  const { currentBank } = useBank();
  const [expandedObservation, setExpandedObservation] = useState<number | null>(null);
  const [regenerateStatus, setRegenerateStatus] = useState<{
    status: "scheduling" | "pending" | "completed" | "failed";
    errorMessage?: string | null;
  } | null>(null);

  // Memory detail modal state
  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null);

  const handleRegenerate = async () => {
    if (!currentBank) return;

    setRegenerateStatus({ status: "scheduling" });
    try {
      const result = await client.refreshMentalModel(currentBank, model.id);
      if (result.operation_id) {
        setRegenerateStatus({ status: "pending" });
        pollRegenerateStatus(result.operation_id);
      }
    } catch (error) {
      console.error("Error refreshing mental model:", error);
      setRegenerateStatus({ status: "failed", errorMessage: (error as Error).message });
      setTimeout(() => setRegenerateStatus(null), 5000);
    }
  };

  const pollRegenerateStatus = async (operationId: string) => {
    if (!currentBank) return;

    const poll = async () => {
      try {
        const status = await client.getOperationStatus(currentBank, operationId);
        if (status.status === "pending") {
          setTimeout(poll, 2000);
        } else if (status.status === "completed") {
          setRegenerateStatus({ status: "completed" });
          onRegenerated?.();
          setTimeout(() => setRegenerateStatus(null), 3000);
        } else {
          setRegenerateStatus({ status: "failed", errorMessage: status.error_message });
          setTimeout(() => setRegenerateStatus(null), 5000);
        }
      } catch (error) {
        console.error("Error polling refresh status:", error);
        setRegenerateStatus(null);
      }
    };

    poll();
  };

  const getSubtypeIcon = (subtype: string) => {
    switch (subtype) {
      case "pinned":
        return <Pin className="w-5 h-5 text-amber-500" />;
      case "structural":
        return <Target className="w-5 h-5 text-blue-500" />;
      case "emergent":
        return <Sparkles className="w-5 h-5 text-emerald-500" />;
      case "learned":
        return <Lightbulb className="w-5 h-5 text-violet-500" />;
      case "directive":
        return <AlertTriangle className="w-5 h-5 text-rose-500" />;
      default:
        return <Lightbulb className="w-5 h-5 text-slate-500" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case "world":
        return "bg-blue-500/10 text-blue-600 dark:text-blue-400";
      case "experience":
        return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
      case "opinion":
        return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
      default:
        return "bg-slate-500/10 text-slate-600 dark:text-slate-400";
    }
  };

  const getTrendColor = (trend: string) => {
    switch (trend) {
      case "stable":
        return "bg-blue-500/10 text-blue-600 dark:text-blue-400";
      case "strengthening":
        return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400";
      case "weakening":
        return "bg-amber-500/10 text-amber-600 dark:text-amber-400";
      case "new":
        return "bg-violet-500/10 text-violet-600 dark:text-violet-400";
      case "stale":
        return "bg-slate-500/10 text-slate-600 dark:text-slate-400";
      default:
        return "bg-slate-500/10 text-slate-600 dark:text-slate-400";
    }
  };

  const getTrendDescription = (trend: string) => {
    switch (trend) {
      case "stable":
        return "Consistently mentioned over time";
      case "strengthening":
        return "Mentioned more frequently recently";
      case "weakening":
        return "Mentioned less frequently recently";
      case "new":
        return "Recently discovered";
      case "stale":
        return "Not mentioned recently";
      default:
        return "";
    }
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-start mb-8 pb-5 border-b border-border">
        <div className="flex items-start gap-3">
          {getSubtypeIcon(model.subtype)}
          <div>
            <h3 className="text-xl font-bold text-foreground">{model.name}</h3>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span
                className={`text-xs px-1.5 py-0.5 rounded ${
                  model.subtype === "pinned"
                    ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                    : model.subtype === "structural"
                      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                      : model.subtype === "learned"
                        ? "bg-violet-500/10 text-violet-600 dark:text-violet-400"
                        : model.subtype === "directive"
                          ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                          : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                }`}
              >
                {model.subtype}
              </span>
              {model.tags && model.tags.length > 0 && (
                <>
                  {model.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground flex items-center gap-1"
                    >
                      <Tag className="w-2.5 h-2.5" />
                      {tag}
                    </span>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={regenerateStatus?.status === "completed" ? "default" : "outline"}
            size="sm"
            onClick={handleRegenerate}
            disabled={
              !!regenerateStatus &&
              regenerateStatus.status !== "completed" &&
              regenerateStatus.status !== "failed"
            }
            className={`h-8 ${
              regenerateStatus?.status === "completed"
                ? "bg-emerald-500 hover:bg-emerald-600"
                : regenerateStatus?.status === "failed"
                  ? "border-rose-500 text-rose-500"
                  : ""
            }`}
          >
            {regenerateStatus?.status === "scheduling" || regenerateStatus?.status === "pending" ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : regenerateStatus?.status === "completed" ? (
              <Check className="w-4 h-4 mr-1" />
            ) : regenerateStatus?.status === "failed" ? (
              <X className="w-4 h-4 mr-1" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-1" />
            )}
            {regenerateStatus?.status === "scheduling"
              ? "Scheduling..."
              : regenerateStatus?.status === "pending"
                ? "Refreshing..."
                : regenerateStatus?.status === "completed"
                  ? "Done!"
                  : regenerateStatus?.status === "failed"
                    ? "Failed"
                    : "Refresh"}
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose} className="h-8 w-8 p-0">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        {/* Description */}
        <div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Description
          </div>
          <div className="prose prose-base dark:prose-invert max-w-none prose-p:leading-relaxed prose-p:text-foreground">
            <ReactMarkdown>{model.description}</ReactMarkdown>
          </div>
        </div>

        {/* Trend Legend - shown when there are observations */}
        {model.observations && model.observations.length > 0 && (
          <div className="p-3 bg-muted/20 rounded-lg border border-border/30">
            <div className="text-[10px] font-medium text-muted-foreground mb-2">Trend Legend</div>
            <div className="grid grid-cols-5 gap-2 text-[10px]">
              <div className="flex flex-col gap-1">
                <span className={`px-1.5 py-0.5 rounded text-center ${getTrendColor("new")}`}>
                  new
                </span>
                <span className="text-muted-foreground text-center">Recently discovered</span>
              </div>
              <div className="flex flex-col gap-1">
                <span
                  className={`px-1.5 py-0.5 rounded text-center ${getTrendColor("strengthening")}`}
                >
                  strengthening
                </span>
                <span className="text-muted-foreground text-center">Mentioned more recently</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className={`px-1.5 py-0.5 rounded text-center ${getTrendColor("stable")}`}>
                  stable
                </span>
                <span className="text-muted-foreground text-center">Consistently mentioned</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className={`px-1.5 py-0.5 rounded text-center ${getTrendColor("weakening")}`}>
                  weakening
                </span>
                <span className="text-muted-foreground text-center">Mentioned less recently</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className={`px-1.5 py-0.5 rounded text-center ${getTrendColor("stale")}`}>
                  stale
                </span>
                <span className="text-muted-foreground text-center">Not mentioned recently</span>
              </div>
            </div>
          </div>
        )}

        {/* Observations */}
        {model.observations && model.observations.length > 0 && (
          <div>
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Observations ({model.observations.length})
            </div>
            <div className="space-y-4">
              {model.observations.map((observation, idx) => {
                const hasEvidence = observation.evidence && observation.evidence.length > 0;

                return (
                  <div key={idx} className="p-4 bg-muted/50 rounded-lg">
                    {/* Title */}
                    <h4 className="text-base font-semibold mb-1 text-foreground break-words">
                      {observation.title}
                    </h4>

                    {/* Trend and date badges */}
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      {observation.trend && (
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded cursor-help ${getTrendColor(observation.trend)}`}
                          title={getTrendDescription(observation.trend)}
                        >
                          {observation.trend}
                        </span>
                      )}
                      {observation.evidence_span?.from && observation.evidence_span?.to && (
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(observation.evidence_span.from).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                          })}{" "}
                          -{" "}
                          {new Date(observation.evidence_span.to).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                          })}
                        </span>
                      )}
                    </div>

                    {/* Content */}
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => (
                            <p className="text-sm leading-relaxed my-2 text-foreground">
                              {children}
                            </p>
                          ),
                          ul: ({ children }) => <ul className="my-2 pl-5 list-disc">{children}</ul>,
                          ol: ({ children }) => (
                            <ol className="my-2 pl-5 list-decimal">{children}</ol>
                          ),
                          li: ({ children }) => (
                            <li className="my-1 text-sm text-foreground">{children}</li>
                          ),
                          code: ({ children }) => (
                            <code className="text-sm bg-muted px-1.5 py-0.5 rounded">
                              {children}
                            </code>
                          ),
                          strong: ({ children }) => (
                            <strong className="font-semibold text-foreground">{children}</strong>
                          ),
                        }}
                      >
                        {observation.text || observation.content}
                      </ReactMarkdown>
                    </div>

                    {/* Evidence section */}
                    {hasEvidence && (
                      <div className="mt-3 pt-2 border-t border-border/50">
                        <button
                          onClick={() =>
                            setExpandedObservation(expandedObservation === idx ? null : idx)
                          }
                          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors group"
                        >
                          <ChevronRight
                            className={`w-3 h-3 transition-transform ${expandedObservation === idx ? "rotate-90" : ""}`}
                          />
                          <FileText className="w-3 h-3" />
                          <span>
                            {observation.evidence!.length} evidence quote
                            {observation.evidence!.length !== 1 ? "s" : ""}
                          </span>
                          <span className="text-muted-foreground/50 group-hover:text-muted-foreground">
                            {expandedObservation === idx ? "Hide" : "Show"}
                          </span>
                        </button>

                        {expandedObservation === idx && (
                          <div className="mt-3 space-y-2 animate-in slide-in-from-top-2 duration-200">
                            {observation.evidence!.map((ev, evIdx) => (
                              <div
                                key={evIdx}
                                className="p-3 bg-background rounded-md border border-border flex items-start justify-between gap-3"
                              >
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm text-foreground italic">
                                    &ldquo;{ev.quote}&rdquo;
                                  </p>
                                  {ev.timestamp && (
                                    <span className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                                      <Calendar className="w-3 h-3" />
                                      {new Date(ev.timestamp).toLocaleDateString("en-US", {
                                        month: "short",
                                        day: "numeric",
                                        year: "numeric",
                                      })}
                                    </span>
                                  )}
                                </div>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="h-7 text-xs shrink-0"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedMemoryId(ev.memory_id);
                                  }}
                                >
                                  <ExternalLink className="w-3 h-3 mr-1" />
                                  View
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
              Observations
            </div>
            <div className="text-2xl font-bold text-foreground">
              {model.observations?.length || 0}
            </div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
              Source Memories
            </div>
            <div className="text-2xl font-bold text-foreground">{getTotalMemoryCount(model)}</div>
          </div>
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
              Last Refreshed
            </div>
            <div className="text-base font-medium text-foreground">
              {model.last_refresh_at
                ? new Date(model.last_refresh_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                  })
                : "Never"}
            </div>
          </div>
        </div>

        {/* Freshness */}
        {model.freshness && (
          <div
            className={`p-4 rounded-lg border ${model.freshness.is_up_to_date ? "bg-emerald-500/5 border-emerald-500/20" : "bg-amber-500/5 border-amber-500/20"}`}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-foreground">
                  {model.freshness.is_up_to_date ? "Up to date" : "Needs refresh"}
                </div>
                {!model.freshness.is_up_to_date && (
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {model.freshness.memories_since_refresh} new memories since last refresh
                  </div>
                )}
              </div>
              <div
                className={`w-3 h-3 rounded-full ${model.freshness.is_up_to_date ? "bg-emerald-500" : "bg-amber-500"}`}
              />
            </div>
          </div>
        )}

        {/* ID */}
        <div className="p-4 bg-muted/50 rounded-lg">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            Model ID
          </div>
          <code className="text-sm font-mono break-all text-muted-foreground">{model.id}</code>
        </div>
      </div>

      {/* Memory Detail Modal */}
      <MemoryDetailModal memoryId={selectedMemoryId} onClose={() => setSelectedMemoryId(null)} />
    </div>
  );
}
