/**
 * api/client.js
 * -------------
 * Centralised fetch wrapper for all Plagiarism Intelligence API calls.
 *
 * Base URL is read from the VITE_API_BASE_URL environment variable so the
 * same build can be pointed at different backends (local dev, staging, prod).
 *
 * Usage:
 *   import { getSubmission, uploadSubmission } from '../api/client'
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${options.method || 'GET'} ${path} → ${res.status}: ${body}`)
  }
  return res.json()
}

// ── Submissions ───────────────────────────────────────────────────────────────

export async function uploadSubmission(formData) {
  /** formData: FormData with file + student_id, assignment_id, instructor_id */
  const res = await fetch(`${BASE_URL}/api/v1/submissions/upload`, {
    method: 'POST',
    body: formData,
    // Don't set Content-Type — let fetch set multipart boundary automatically
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Upload failed → ${res.status}: ${body}`)
  }
  return res.json()
}

export function processSubmission(submissionId) {
  return request(`/api/v1/submissions/${submissionId}/process`, { method: 'POST' })
}

export function scoreSubmission(submissionId) {
  return request(`/api/v1/submissions/${submissionId}/score`, { method: 'POST' })
}

export function getSubmission(submissionId) {
  return request(`/api/v1/submissions/${submissionId}`)
}

export function listSubmissions({ assignmentId, instructorId } = {}) {
  const params = new URLSearchParams()
  if (assignmentId) params.set('assignment_id', assignmentId)
  if (instructorId) params.set('instructor_id', instructorId)
  const qs = params.toString() ? `?${params}` : ''
  return request(`/api/v1/submissions${qs}`)
}

export function getSubmissionFlags(submissionId) {
  return request(`/api/v1/submissions/${submissionId}/flags`)
}

// ── Flags ─────────────────────────────────────────────────────────────────────

export function getFlag(flagId) {
  return request(`/api/v1/flags/${flagId}`)
}

export function setFlagDecision(flagId, decision) {
  /** decision: "confirmed" | "dismissed" */
  return request(`/api/v1/flags/${flagId}/decision`, {
    method: 'PATCH',
    body: JSON.stringify({ decision }),
  })
}

// ── Instructors ───────────────────────────────────────────────────────────────

export function getBaseline(instructorId, assignmentId) {
  return request(
    `/api/v1/instructors/${instructorId}/baseline?assignment_id=${assignmentId}`
  )
}

export function rebuildBaseline(instructorId, assignmentId) {
  return request(
    `/api/v1/instructors/${instructorId}/baseline/rebuild?assignment_id=${assignmentId}`,
    { method: 'POST' }
  )
}
