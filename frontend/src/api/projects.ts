import axios from "axios"

import type {
  Project,
  ProjectCreate,
  ProjectEntity,
  FrontendRequestDiagnostics,
  ProjectStats,
  ScanSummary,
  VectorIndexSummary,
  VectorIndexStatus,
} from "@/types/project"

export async function createProject(data: ProjectCreate): Promise<Project> {
  const response = await axios.post<Project>("/api/projects", data)
  return response.data
}

export async function listProjects(): Promise<Project[]> {
  return (await axios.get<Project[]>("/api/projects")).data
}

export async function reorderProjects(projectIds: number[]): Promise<Project[]> {
  return (await axios.put<Project[]>("/api/projects/order", {
    project_ids: projectIds,
  })).data
}

export async function deleteProject(projectId: number): Promise<void> {
  await axios.delete(`/api/projects/${projectId}`)
}

export async function getProjectEntity(
  projectId: number,
  entityId: number,
): Promise<ProjectEntity> {
  const response = await axios.get<ProjectEntity>(
    `/api/projects/${projectId}/entities/${entityId}`,
  )
  return response.data
}

export async function scanProject(projectId: number): Promise<ScanSummary> {
  const response = await axios.post<ScanSummary>(
    `/api/projects/${projectId}/scan`,
  )
  return response.data
}

export async function getProjectStats(
  projectId: number,
): Promise<ProjectStats> {
  const response = await axios.get<ProjectStats>(
    `/api/projects/${projectId}/stats`,
  )
  return response.data
}

export async function getFrontendRequestDiagnostics(
  projectId: number,
  limit = 10,
): Promise<FrontendRequestDiagnostics> {
  const response = await axios.get<FrontendRequestDiagnostics>(
    `/api/projects/${projectId}/frontend-request-diagnostics`,
    { params: { limit } },
  )
  return response.data
}

export async function buildVectorIndex(
  projectId: number,
): Promise<VectorIndexSummary> {
  const response = await axios.post<VectorIndexSummary>(
    `/api/projects/${projectId}/build-vector-index`,
  )
  return response.data
}

export async function getVectorIndexStatus(
  projectId: number,
): Promise<VectorIndexStatus> {
  return (await axios.get<VectorIndexStatus>(
    `/api/projects/${projectId}/vector-index-status`,
  )).data
}
