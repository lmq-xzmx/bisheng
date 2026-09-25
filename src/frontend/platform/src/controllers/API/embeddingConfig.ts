// F050: Embedding query configuration API
import axios from "@/controllers/request"

export type EmbeddingQueryStrategy = "new_only" | "old_only" | "dual_rrf"

export interface EmbeddingConfig {
  strategy: EmbeddingQueryStrategy
  show_details: boolean
}

export async function getEmbeddingConfig(): Promise<EmbeddingConfig> {
  return await axios.get("/api/v1/llm/embedding-config")
}

export async function updateEmbeddingConfig(config: EmbeddingConfig): Promise<EmbeddingConfig> {
  return await axios.put("/api/v1/llm/embedding-config", config)
}
