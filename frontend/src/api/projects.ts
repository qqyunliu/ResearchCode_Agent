import axios from "axios"

import type {
  Project,
  ProjectCreate,
  ProjectEntity,
  ProjectStats,
  ScanSummary,
} from "@/types/project"

export async function createProject(data: ProjectCreate): Promise<Project> {
  const response = await axios.post<Project>("/api/projects", data)
  return response.data
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
