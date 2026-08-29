import apiClient from "./client";

export const advancedApi = {
  // Phase 49 threat intel
  threatIntelStatus: () => apiClient.get("/threat-intel/status"),
  enrichIp: (ip: string) => apiClient.get(`/threat-intel/enrich/ip/${ip}`),
  enrichDomain: (d: string) => apiClient.get(`/threat-intel/enrich/domain/${d}`),
  enrichAlert: (alertId: number) => apiClient.post(`/threat-intel/enrich/alert/${alertId}`),

  // Phase 50 soar exec
  soarTargets: () => apiClient.get("/soar-exec/targets"),
  soarPending: () => apiClient.get("/soar-exec/pending"),
  soarApprove: (actionId: string) => apiClient.post(`/soar-exec/execute/${actionId}/approve`),
  soarDryRun: (alert: any) => apiClient.post("/soar-exec/dry-run", { alert }),

  // Phase 51 collaboration
  listComments: (caseId: number) => apiClient.get(`/cases/${caseId}/comments`),
  createComment: (caseId: number, content: string) => apiClient.post(`/cases/${caseId}/comments`, { content }),
  listActivities: (caseId: number) => apiClient.get(`/cases/${caseId}/activities`),

  // Phase 52 sigma
  listSigma: () => apiClient.get("/sigma/rules"),
  createSigma: (payload: any) => apiClient.post("/sigma/rules", payload),
  listDsl: () => apiClient.get("/sigma/dsl"),
  createDsl: (payload: any) => apiClient.post("/sigma/dsl", payload),
  testSigma: (id: number, alert: any) => apiClient.post(`/sigma/rules/${id}/test`, alert),

  // Phase 53 compliance packs
  listPacks: () => apiClient.get("/compliance-packs"),
  getPack: (name: string) => apiClient.get(`/compliance-packs/${name}`),
  exportPackS3: (name: string) => apiClient.post(`/compliance-packs/${name}/export/s3`),
  listSchedules: () => apiClient.get("/compliance-packs/schedules/list"),

  // Phase 54 teams
  listTeams: () => apiClient.get("/org/teams"),
  createTeam: (payload: any) => apiClient.post("/org/teams", payload),
  listInvites: () => apiClient.get("/org/invites"),
  createInvite: (payload: any) => apiClient.post("/org/invites", payload),

  // Phase 55 ml feedback
  submitFeedback: (payload: any) => apiClient.post("/ml/feedback", payload),
  feedbackStats: () => apiClient.get("/ml/feedback/stats"),
  drift: () => apiClient.get("/ml/drift"),
  mlModels: () => apiClient.get("/ml/models"),

  // Phase 56 ATT&CK
  attackMatrix: () => apiClient.get("/attack/matrix"),
  attackHeatmap: () => apiClient.get("/attack/heatmap"),
  attackActors: () => apiClient.get("/attack/actors"),
  attributeActor: (techniques: string[]) => apiClient.post("/attack/attribute", techniques),
  timelineExport: (caseId: number, format: string = "json") => apiClient.get(`/attack/timeline/${caseId}/export?format=${format}`),

  // Phase 57 data lifecycle
  retentionPolicies: () => apiClient.get("/data-lifecycle/policies"),
  runArchive: (dryRun = true) => apiClient.post(`/data-lifecycle/archive/run?dry_run=${dryRun}`),
  legalHolds: () => apiClient.get("/data-lifecycle/legal-holds"),
  gdprRequests: () => apiClient.get("/data-lifecycle/gdpr/requests"),

  // Phase 58 HA
  haStatus: () => apiClient.get("/ha/status"),

  // Phase 59 PWA
  pwaManifest: () => apiClient.get("/pwa/manifest"),
  pwaStatus: () => apiClient.get("/pwa/status"),

  // Phase 60 billing
  billingPlans: () => apiClient.get("/billing/plans"),
  billingQuota: () => apiClient.get("/billing/quota"),
  billingUsage: () => apiClient.get("/billing/usage"),
};
