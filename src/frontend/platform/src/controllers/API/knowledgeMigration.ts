// F050: Embedding model migration API endpoints
import axios from "@/controllers/request"

export interface MigrationStatus {
  kb_id: number
  kb_name: string
  current_model: string | null
  target_model: string | null
  migration_status: "idle" | "pending_delayed" | "pending_immediate" | "migrating" | "completed" | "locked" | "failed"
  migration_progress: number
  locked_at: string | null
  locked_by: string | null
  locked_model: string | null
  estimated_total_docs?: number
}

export interface MigrationSummary {
  items: MigrationStatus[]
  total: number
}

export interface MigrationStartReq {
  target_model: string
  strategy: "immediate" | "delayed"
}

export async function getMigrationSummary(): Promise<MigrationStatus[]> {
  return await axios.get("/api/v1/knowledge/migration/summary")
}

export async function getMigrationStatus(kbId: number): Promise<MigrationStatus> {
  return await axios.get(`/api/v1/knowledge/${kbId}/migration`)
}

export async function startMigration(kbId: number, req: MigrationStartReq): Promise<MigrationStatus> {
  return await axios.post(`/api/v1/knowledge/${kbId}/migration/start`, req)
}

export async function pauseMigration(kbId: number): Promise<MigrationStatus> {
  return await axios.post(`/api/v1/knowledge/${kbId}/migration/pause`)
}

export async function forceCompleteMigration(kbId: number): Promise<MigrationStatus> {
  return await axios.post(`/api/v1/knowledge/${kbId}/migration/complete`)
}

export async function lockKnowledgeBase(kbId: number): Promise<MigrationStatus> {
  return await axios.post(`/api/v1/knowledge/${kbId}/migration/lock`)
}

export async function unlockKnowledgeBase(kbId: number): Promise<MigrationStatus> {
  return await axios.post(`/api/v1/knowledge/${kbId}/migration/unlock`)
}
