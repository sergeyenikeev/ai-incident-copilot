{{- define "ai-incident-copilot.name" -}}
{{- /* Базовое имя chart'а, от которого строятся resource names. */ -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ai-incident-copilot.fullname" -}}
{{- /* Полное имя ресурса с учётом возможного override. */ -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "ai-incident-copilot.name" . -}}
{{- end -}}
{{- end -}}

{{- define "ai-incident-copilot.labels" -}}
{{- /* Единый набор labels для всех ресурсов chart'а. */ -}}
app.kubernetes.io/name: {{ include "ai-incident-copilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
