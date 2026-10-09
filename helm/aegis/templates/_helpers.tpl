{{/*
AEGIS Helm chart helpers.
*/}}

{{- define "aegis.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aegis.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "aegis.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "aegis.labels" -}}
helm.sh/chart: {{ include "aegis.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{- define "aegis.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "aegis.backend.labels" -}}
{{ include "aegis.labels" . }}
{{ include "aegis.backend.selectorLabels" . }}
{{- end }}

{{- define "aegis.backend.selectorLabels" -}}
{{ include "aegis.selectorLabels" . }}
app.kubernetes.io/name: aegis-backend
app.kubernetes.io/component: backend
{{- end }}

{{- define "aegis.mlService.labels" -}}
{{ include "aegis.labels" . }}
{{ include "aegis.mlService.selectorLabels" . }}
{{- end }}

{{- define "aegis.mlService.selectorLabels" -}}
{{ include "aegis.selectorLabels" . }}
app.kubernetes.io/name: aegis-ml-service
app.kubernetes.io/component: ml-service
{{- end }}

{{- define "aegis.dashboard.labels" -}}
{{ include "aegis.labels" . }}
{{ include "aegis.dashboard.selectorLabels" . }}
{{- end }}

{{- define "aegis.dashboard.selectorLabels" -}}
{{ include "aegis.selectorLabels" . }}
app.kubernetes.io/name: aegis-dashboard
app.kubernetes.io/component: dashboard
{{- end }}
