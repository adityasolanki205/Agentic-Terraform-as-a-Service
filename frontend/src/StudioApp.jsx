import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Send, User, Briefcase, Loader2, LogOut, Lock,
  Terminal, Database, Cloud, Code2, Play, CheckCircle2, XCircle, RefreshCw,
  BookOpen, Layers, AlertTriangle, Trash2, RotateCcw, Save, Sparkles,
  Server, Activity, Search, PlusCircle, FileCode, MessageSquare, Plus,
  ChevronDown, PanelRightClose, PanelRightOpen, Check, ShieldCheck
} from 'lucide-react'
import './StudioLight.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

// Exact starter templates from \terraform_starters so Pre-Plan Code is ALWAYS visible immediately
const DEFAULT_STARTER_FILES = {
  'bucket.tf': {
    content: `# Google Cloud Storage bucket resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/bucket.tf.
resource "google_storage_bucket" "requested" {
  name                        = var.resource_config["bucket_name"]
  project                     = var.project_id
  location                    = var.location
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = lookup(var.resource_config, "versioning", true)
  }
}`,
    starter_content: `# Google Cloud Storage bucket resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/bucket.tf.
resource "google_storage_bucket" "requested" {
  name                        = var.resource_config["bucket_name"]
  project                     = var.project_id
  location                    = var.location
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = lookup(var.resource_config, "versioning", true)
  }
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/storage_bucket/bucket.tf',
    is_artifact: false,
    has_resources: false
  },
  'dataset.tf': {
    content: `# BigQuery dataset resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/dataset.tf.
resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.resource_config["dataset_id"]
  location   = var.location
}`,
    starter_content: `# BigQuery dataset resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/dataset.tf.
resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.resource_config["dataset_id"]
  location   = var.location
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/bigquery_dataset/dataset.tf',
    is_artifact: false,
    has_resources: false
  },
  'table.tf': {
    content: `# BigQuery table resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/table.tf.
resource "google_bigquery_table" "requested" {
  project             = var.project_id
  dataset_id          = var.resource_config["dataset_id"]
  table_id            = var.resource_config["table_id"]
  deletion_protection = false

  schema = lookup(var.resource_config, "schema", null)
}`,
    starter_content: `# BigQuery table resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/table.tf.
resource "google_bigquery_table" "requested" {
  project             = var.project_id
  dataset_id          = var.resource_config["dataset_id"]
  table_id            = var.resource_config["table_id"]
  deletion_protection = false

  schema = lookup(var.resource_config, "schema", null)
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/bigquery_table/table.tf',
    is_artifact: false,
    has_resources: false
  },
  'topic.tf': {
    content: `# Google Cloud Pub/Sub topic resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/topic.tf.
resource "google_pubsub_topic" "requested" {
  name    = var.resource_config["topic_name"]
  project = var.project_id
}`,
    starter_content: `# Google Cloud Pub/Sub topic resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/topic.tf.
resource "google_pubsub_topic" "requested" {
  name    = var.resource_config["topic_name"]
  project = var.project_id
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/pubsub_topic/topic.tf',
    is_artifact: false,
    has_resources: false
  },
  'subscription.tf': {
    content: `# Google Cloud Pub/Sub subscription resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/subscription.tf.
resource "google_pubsub_subscription" "requested" {
  name                       = var.resource_config["subscription_name"]
  topic                      = var.resource_config["topic"]
  project                    = var.project_id
  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 20
}`,
    starter_content: `# Google Cloud Pub/Sub subscription resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/subscription.tf.
resource "google_pubsub_subscription" "requested" {
  name                       = var.resource_config["subscription_name"]
  topic                      = var.resource_config["topic"]
  project                    = var.project_id
  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 20
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/pubsub_subscription/subscription.tf',
    is_artifact: false,
    has_resources: false
  },
  'main.tf': {
    content: `terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 8.0"
    }
  }

  # The bucket name is supplied during terraform init. It must already exist.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}`,
    starter_content: `terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 8.0"
    }
  }

  # The bucket name is supplied during terraform init. It must already exist.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/common/main.tf',
    is_artifact: false,
    has_resources: false
  },
  'variables.tf': {
    content: `variable "project_id" {
  description = "Google Cloud project ID explicitly provided for this request."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6-30 characters, start with a lowercase letter, and contain lowercase letters, numbers, or hyphens."
  }
}

variable "location" {
  description = "Google Cloud location explicitly provided for this request."
  type        = string
  default     = "asia-south2"

  validation {
    condition     = can(regex("^[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?$", var.location))
    error_message = "Location must contain letters, numbers, or hyphens and cannot start or end with a hyphen."
  }
}`,
    starter_content: `variable "project_id" {
  description = "Google Cloud project ID explicitly provided for this request."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6-30 characters, start with a lowercase letter, and contain lowercase letters, numbers, or hyphens."
  }
}

variable "location" {
  description = "Google Cloud location explicitly provided for this request."
  type        = string
  default     = "asia-south2"

  validation {
    condition     = can(regex("^[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?$", var.location))
    error_message = "Location must contain letters, numbers, or hyphens and cannot start or end with a hyphen."
  }
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/common/variables.tf',
    is_artifact: false,
    has_resources: false
  }
}

const ARTIFACT_FILE_LIST = [
  { name: 'bucket.tf', label: 'bucket.tf', desc: 'GCS Buckets' },
  { name: 'dataset.tf', label: 'dataset.tf', desc: 'BigQuery Datasets' },
  { name: 'table.tf', label: 'table.tf', desc: 'BigQuery Tables' },
  { name: 'topic.tf', label: 'topic.tf', desc: 'Pub/Sub Topics' },
  { name: 'subscription.tf', label: 'subscription.tf', desc: 'Pub/Sub Subscriptions' },
  { name: 'main.tf', label: 'main.tf', desc: 'Provider & GCS Backend' },
  { name: 'variables.tf', label: 'variables.tf', desc: 'Input Variables' }
]

const CATEGORY_METADATA = {
  storage_bucket: { label: 'Cloud Storage Buckets', file: 'bucket.tf', icon: Cloud },
  bigquery_dataset: { label: 'BigQuery Datasets', file: 'dataset.tf', icon: Database },
  bigquery_table: { label: 'BigQuery Tables', file: 'table.tf', icon: Database },
  pubsub_topic: { label: 'Pub/Sub Topics', file: 'topic.tf', icon: Server },
  pubsub_subscription: { label: 'Pub/Sub Subscriptions', file: 'subscription.tf', icon: Server }
}

const INITIAL_WELCOME_MSG = {
  role: 'assistant',
  content:
    '### Welcome to Terraform-as-a-Service\n\n' +
    'Project: **`solar-dialect-264808`** • Region: **`asia-south2`** • State: **`gs://.../taas/solar-dialect-264808/gcp`**\n\n' +
    '- **Pre-Plan Code**: Starter templates from `\\terraform_starters` and created resources from `artifacts/gcp` are loaded in the sidecar panel.\n' +
    '- **Customize & Plan**: Edit any `.tf` file directly or ask me in chat, then click **Plan**.'
}

export default function StudioApp() {
  // Authentication & Role State
  const [authUser, setAuthUser] = useState({
    username: 'dev',
    role: 'developer',
    displayName: 'Cloud Developer'
  })
  const [usernameInput, setUsernameInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [loginError, setLoginError] = useState('')

  // Custom Rounded Service Dropdown ('taas' | 'dataops')
  const [selectedService, setSelectedService] = useState('taas')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef(null)

  // Antigravity-style Right Workbench Panel: Minimize state + Cursor-Draggable Width (%)
  const [panelCollapsed, setPanelCollapsed] = useState(false)
  const [panelWidthPct, setPanelWidthPct] = useState(54)
  const [isDraggingPanel, setIsDraggingPanel] = useState(false)
  const workspaceContainerRef = useRef(null)

  // Active Resources Filter State
  const [resourceFilter, setResourceFilter] = useState('all')
  const [resourceSearch, setResourceSearch] = useState('')

  // ============================================================================
  // CHATS & HISTORY STATE
  // ============================================================================
  const [chatSessions, setChatSessions] = useState([
    {
      id: 'session-1',
      title: 'GCS & BigQuery Provisioning',
      service: 'taas',
      createdAt: 'Just now',
      messages: [INITIAL_WELCOME_MSG]
    }
  ])
  const [activeSessionId, setActiveSessionId] = useState('session-1')

  const activeSession = chatSessions.find(s => s.id === activeSessionId) || chatSessions[0]
  const taasMessages = activeSession ? activeSession.messages : [INITIAL_WELCOME_MSG]

  const updateActiveSessionMessages = (updater) => {
    setChatSessions(prev =>
      prev.map(session => {
        if (session.id !== activeSessionId) return session
        const nextMsgs = typeof updater === 'function' ? updater(session.messages) : updater
        const firstUserMsg = nextMsgs.find(m => m.role === 'user')
        const nextTitle = firstUserMsg
          ? firstUserMsg.content.slice(0, 34) + (firstUserMsg.content.length > 34 ? '...' : '')
          : session.title
        return { ...session, messages: nextMsgs, title: nextTitle }
      })
    )
  }

  const handleNewChat = () => {
    const newId = `session-${Date.now()}`
    const isDataOps = selectedService === 'dataops'
    const newSession = {
      id: newId,
      title: isDataOps ? 'New DataOps Query' : 'New Infrastructure Chat',
      service: selectedService,
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      messages: [
        isDataOps
          ? {
            role: 'assistant',
            content: 'Welcome to **Agentic DataOps**. Ask about ServiceNow incidents, MTTR, or backlog aging in `solar-dialect-264808.servicenow_itsm.incidents`.'
          }
          : INITIAL_WELCOME_MSG
      ]
    }
    setChatSessions(prev => [newSession, ...prev])
    setActiveSessionId(newId)
  }

  const handleDeleteChatSession = (e, idToDelete) => {
    e.stopPropagation()
    if (chatSessions.length <= 1) {
      handleNewChat()
      setChatSessions(prev => prev.filter(s => s.id !== idToDelete))
      return
    }
    const remaining = chatSessions.filter(s => s.id !== idToDelete)
    setChatSessions(remaining)
    if (activeSessionId === idToDelete) {
      setActiveSessionId(remaining[0].id)
    }
  }

  // ============================================================================
  // TERRAFORM-AS-A-SERVICE (TaaS Studio) STATE
  // ============================================================================
  const [taasInput, setTaasInput] = useState('')
  const [taasLoading, setTaasLoading] = useState(false)
  const [taasRightTab, setTaasRightTab] = useState('editor')

  // Pre-Plan Code Editor State
  const [artifactFiles, setArtifactFiles] = useState(DEFAULT_STARTER_FILES)
  const [selectedFile, setSelectedFile] = useState('bucket.tf')
  const [editorContent, setEditorContent] = useState(DEFAULT_STARTER_FILES['bucket.tf'].content)
  const [editorDirty, setEditorDirty] = useState(false)
  const [savingFile, setSavingFile] = useState(false)
  const [editorStatusMsg, setEditorStatusMsg] = useState('')

  // Pending Plan & Mandatory Approval Gate State
  const [pendingPlan, setPendingPlan] = useState(null)
  const [approvalDecision, setApprovalDecision] = useState('apply')
  const [runningPlanOrApply, setRunningPlanOrApply] = useState(false)

  // Active & Deactivated Cloud Resources State
  const [taasResources, setTaasResources] = useState({ active: {}, deactivated: {}, active_count: 0 })
  const [loadingResources, setLoadingResources] = useState(false)

  // Live Terraform Docs Lookup State (No Cache)
  const [docResourceType, setDocResourceType] = useState('google_storage_bucket')
  const [docQuery, setDocQuery] = useState('labels lifecycle_rule')
  const [docResult, setDocResult] = useState(null)
  const [loadingDocs, setLoadingDocs] = useState(false)

  // Basic EnterpriseGPT State (for HR / Employee roles)
  const [basicChatInput, setBasicChatInput] = useState('')
  const [basicChatLoading, setBasicChatLoading] = useState(false)
  const [entMessages, setEntMessages] = useState([
    {
      role: 'assistant',
      content: 'Welcome to **EnterpriseGPT**. Ask about HR bench employees, candidate resumes, or company policies.'
    }
  ])

  const taasChatEndRef = useRef(null)

  // Close custom dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Cursor-dragging resize handler for the Pre-Plan / Sidecar Panel (like Antigravity UI)
  useEffect(() => {
    if (!isDraggingPanel) return

    const handleMouseMove = (e) => {
      const container = workspaceContainerRef.current
      if (!container) return
      const rect = container.getBoundingClientRect()
      if (rect.width <= 0) return
      const rightWidthPx = rect.right - e.clientX
      const nextPct = (rightWidthPx / rect.width) * 100
      const clamped = Math.min(76, Math.max(26, nextPct))
      setPanelWidthPct(clamped)
    }

    const handleMouseUp = () => {
      setIsDraggingPanel(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isDraggingPanel])

  useEffect(() => {
    taasChatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [taasMessages])

  useEffect(() => {
    if (authUser?.role === 'developer') {
      fetchTaasArtifacts()
      fetchTaasResources()
    }
  }, [authUser])

  const authenticate = (user, pass) => {
    const u = user.trim().toLowerCase()
    const p = pass.trim()
    if (u === 'dev' && p === 'dev') {
      setAuthUser({ username: 'dev', role: 'developer', displayName: 'Cloud Developer' })
      setSelectedService('taas')
      setLoginError('')
    } else if (u === 'admin' && p === 'admin') {
      setAuthUser({ username: 'admin', role: 'hr', displayName: 'HR Administrator' })
      setLoginError('')
    } else if (u === 'user' && p === 'user') {
      setAuthUser({ username: 'user', role: 'employee', displayName: 'Enterprise Employee' })
      setLoginError('')
    } else {
      setLoginError('Use dev/dev (Developer), admin/admin (HR), or user/user (Employee).')
    }
  }

  const normalizeBackendFiles = (incomingFiles, rawFiles = {}) => {
    const merged = { ...DEFAULT_STARTER_FILES }
    if (incomingFiles && typeof incomingFiles === 'object') {
      Object.entries(incomingFiles).forEach(([fname, val]) => {
        if (typeof val === 'string') {
          merged[fname] = {
            ...(merged[fname] || {}),
            content: val,
            source: 'artifacts/gcp',
            source_path: `artifacts/gcp/${fname}`,
            is_artifact: true,
            has_resources: val.includes('resource "')
          }
        } else if (val && typeof val === 'object') {
          merged[fname] = {
            ...(merged[fname] || {}),
            ...val,
            content: val.content || merged[fname]?.content || ''
          }
        }
      })
    }
    if (rawFiles && typeof rawFiles === 'object') {
      Object.entries(rawFiles).forEach(([fname, txt]) => {
        if (typeof txt === 'string' && txt.trim()) {
          merged[fname] = {
            ...(merged[fname] || {}),
            content: txt
          }
        }
      })
    }
    return merged
  }

  const fetchTaasArtifacts = async (preferredFile = null) => {
    try {
      const res = await axios.get(`${API_BASE}/api/taas/artifacts`)
      const merged = normalizeBackendFiles(res.data.files, res.data.raw_files)
      setArtifactFiles(merged)

      const targetFile = preferredFile || selectedFile
      if (merged[targetFile] && !editorDirty) {
        setEditorContent(merged[targetFile].content)
      }
      if (res.data.pending_plan && res.data.pending_plan.status === 'AWAITING_APPROVAL') {
        setPendingPlan(res.data.pending_plan)
      } else {
        setPendingPlan(null)
      }
    } catch (err) {
      console.warn('Using starter templates fallback:', err.message)
    }
  }

  const fetchTaasResources = async () => {
    setLoadingResources(true)
    try {
      const res = await axios.get(`${API_BASE}/api/taas/resources`)
      setTaasResources(res.data)
    } catch (err) {
      console.warn('Could not load active resources:', err.message)
    } finally {
      setLoadingResources(false)
    }
  }

  const handleSelectArtifactFile = (fileName) => {
    setSelectedFile(fileName)
    setEditorDirty(false)
    setEditorStatusMsg('')
    const fileObj = artifactFiles[fileName] || DEFAULT_STARTER_FILES[fileName]
    setEditorContent(fileObj ? fileObj.content : '')
  }

  const handleLoadStarterTemplate = () => {
    const starter =
      artifactFiles[selectedFile]?.starter_content ||
      DEFAULT_STARTER_FILES[selectedFile]?.starter_content ||
      DEFAULT_STARTER_FILES[selectedFile]?.content ||
      ''
    if (starter) {
      setEditorContent(starter)
      setEditorDirty(true)
      setEditorStatusMsg(`Loaded original starter template from \\terraform_starters for ${selectedFile}.`)
    }
  }

  const handleSaveArtifactCode = async () => {
    setSavingFile(true)
    setEditorStatusMsg('Copying changes to artifacts/gcp & running terraform fmt...')
    try {
      const res = await axios.post(`${API_BASE}/api/taas/artifacts/update`, {
        file_name: selectedFile,
        code_content: editorContent
      })
      if (res.data.status === 'SUCCESS') {
        const updatedText = res.data.content || res.data.updated_content || editorContent
        setEditorContent(updatedText)
        setEditorDirty(false)
        setEditorStatusMsg(`✓ Saved to artifacts/gcp/${selectedFile} (${res.data.formatting || 'formatted'}).`)
        if (res.data.files) {
          setArtifactFiles(normalizeBackendFiles(res.data.files, res.data.raw_files))
        }
      } else {
        setEditorStatusMsg(`Error: ${res.data.message}`)
      }
    } catch (err) {
      setEditorStatusMsg(`Save failed: ${err.response?.data?.detail || err.message}`)
    } finally {
      setSavingFile(false)
    }
  }

  const handleRunTerraformPlan = async () => {
    if (editorDirty) {
      await handleSaveArtifactCode()
    }
    setRunningPlanOrApply(true)
    updateActiveSessionMessages(prev => [
      ...prev,
      { role: 'user', content: `Run \`terraform plan\` on \`artifacts/gcp/${selectedFile}\`` }
    ])
    try {
      const res = await axios.post(`${API_BASE}/api/taas/plan`, {
        file_name: selectedFile
      })
      const data = res.data
      if (data.status === 'AWAITING_APPROVAL') {
        const planObj = data.pending_plan || {
          plan_id: data.plan_id || data.request_id,
          request_id: data.request_id || data.plan_id,
          plan_sha256: data.plan_sha256,
          status: 'AWAITING_APPROVAL',
          plan_summary: data.plan_summary
        }
        setPendingPlan(planObj)
        updateActiveSessionMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content:
              `### Terraform Plan Ready (\`${planObj.plan_id}\`)\n\n` +
              `\`\`\`hcl\n${(data.plan_output || data.plan_summary || '').slice(-2500)}\n\`\`\`\n\n` +
              `Use the **Approval Gate** below to select **\`apply\`** or **\`dont apply\`**.`
          }
        ])
      } else {
        updateActiveSessionMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `### Plan Status: \`${data.status}\`\n\n${data.message || ''}\n\n\`\`\`\n${data.details || ''}\n\`\`\``
          }
        ])
      }
      await fetchTaasArtifacts(selectedFile)
    } catch (err) {
      updateActiveSessionMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error running terraform plan: ${err.response?.data?.detail || err.message}` }
      ])
    } finally {
      setRunningPlanOrApply(false)
    }
  }

  const handleConfirmPlanDecision = async () => {
    if (!pendingPlan) return
    setRunningPlanOrApply(true)
    updateActiveSessionMessages(prev => [
      ...prev,
      { role: 'user', content: `Approval Gate Decision: **${approvalDecision}** for plan \`${pendingPlan.plan_id}\`` }
    ])
    try {
      const res = await axios.post(`${API_BASE}/api/taas/approve`, {
        decision: approvalDecision,
        plan_id: pendingPlan.plan_id,
        request_id: pendingPlan.request_id || pendingPlan.plan_id,
        plan_sha256: pendingPlan.plan_sha256
      })
      const data = res.data
      if (data.status === 'SUCCESS') {
        updateActiveSessionMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content:
              `### Terraform Apply Succeeded (\`${data.plan_id}\`)\n\n` +
              `${data.message}\n\n` +
              `*State file synced to GCS bucket.*\n\n` +
              `\`\`\`\n${(data.apply_output || '').slice(-1800)}\n\`\`\``
          }
        ])
        setPendingPlan(null)
      } else if (data.status === 'CANCELLED') {
        updateActiveSessionMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `### Plan Cancelled (\`${data.plan_id}\`)\n\n${data.message}`
          }
        ])
        setPendingPlan(null)
      } else {
        updateActiveSessionMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `### Apply Status: \`${data.status}\`\n\n${data.message || ''}\n\n\`\`\`\n${data.details || ''}\n\`\`\``
          }
        ])
      }
      await fetchTaasArtifacts(selectedFile)
      await fetchTaasResources()
    } catch (err) {
      updateActiveSessionMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error confirming plan decision: ${err.response?.data?.detail || err.message}` }
      ])
    } finally {
      setRunningPlanOrApply(false)
    }
  }

  const handleChatSend = async (customPrompt = null) => {
    const promptText = (customPrompt ?? taasInput).trim()
    if (!promptText || taasLoading) return

    updateActiveSessionMessages(prev => [...prev, { role: 'user', content: promptText }])
    if (!customPrompt) setTaasInput('')
    setTaasLoading(true)

    if (selectedService === 'dataops') {
      try {
        const res = await axios.post(`${API_BASE}/api/dataops/chat`, {
          message: promptText,
          session_id: activeSessionId
        })
        updateActiveSessionMessages(prev => [
          ...prev,
          { role: 'assistant', content: res.data.response || 'Completed.' }
        ])
      } catch (err) {
        updateActiveSessionMessages(prev => [
          ...prev,
          { role: 'assistant', content: `Error querying Agentic DataOps: ${err.message}` }
        ])
      } finally {
        setTaasLoading(false)
      }
      return
    }

    try {
      const res = await axios.post(`${API_BASE}/api/taas/chat`, {
        message: promptText,
        session_id: activeSessionId
      })
      updateActiveSessionMessages(prev => [
        ...prev,
        { role: 'assistant', content: res.data.response || 'Completed.' }
      ])
      const merged = normalizeBackendFiles(res.data.files, res.data.raw_files)
      setArtifactFiles(merged)

      const activeFile = res.data.active_file || selectedFile
      if (merged[activeFile]) {
        setSelectedFile(activeFile)
        setEditorContent(merged[activeFile].content)
        setEditorDirty(false)
      }
      if (res.data.pending_plan && res.data.pending_plan.status === 'AWAITING_APPROVAL') {
        setPendingPlan(res.data.pending_plan)
      } else {
        setPendingPlan(null)
      }
      fetchTaasResources()
    } catch (err) {
      updateActiveSessionMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error communicating with TaaS Agent: ${err.response?.data?.detail || err.message}` }
      ])
    } finally {
      setTaasLoading(false)
    }
  }

  const handleLookupDocs = async (e) => {
    if (e) e.preventDefault()
    setLoadingDocs(true)
    try {
      const res = await axios.post(`${API_BASE}/api/taas/docs`, {
        resource_type: docResourceType,
        query: docQuery
      })
      setDocResult(res.data)
    } catch (err) {
      setDocResult({ status: 'ERROR', message: err.response?.data?.detail || err.message })
    } finally {
      setLoadingDocs(false)
    }
  }

  const handleInsertSnippetToEditor = (snippet, targetFile = null) => {
    const fileMap = {
      google_storage_bucket: 'bucket.tf',
      google_bigquery_dataset: 'dataset.tf',
      google_bigquery_table: 'table.tf',
      google_pubsub_topic: 'topic.tf',
      google_pubsub_subscription: 'subscription.tf'
    }
    const destFile = targetFile || fileMap[docResourceType] || selectedFile
    const existing = artifactFiles[destFile]?.content || DEFAULT_STARTER_FILES[destFile]?.content || ''
    const combined = `${existing.trimEnd()}\n\n${snippet.trim()}\n`
    setSelectedFile(destFile)
    setEditorContent(combined)
    setEditorDirty(true)
    setTaasRightTab('editor')
    if (panelCollapsed) setPanelCollapsed(false)
    setEditorStatusMsg(`Inserted snippet into ${destFile}. Click "Save to Artifacts" to update artifacts/gcp/${destFile}.`)
  }

  const handleDeactivateResource = async (category, resourceName) => {
    setLoadingResources(true)
    try {
      const res = await axios.post(`${API_BASE}/api/taas/resources/deactivate`, {
        resource_category: category,
        resource_name: resourceName
      })
      updateActiveSessionMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `**Deactivation Plan Created for \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}`
        }
      ])
      await fetchTaasArtifacts(selectedFile)
      await fetchTaasResources()
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingResources(false)
    }
  }

  const handleReactivateResource = async (category, resourceName) => {
    setLoadingResources(true)
    try {
      const res = await axios.post(`${API_BASE}/api/taas/resources/reactivate`, {
        resource_category: category,
        resource_name: resourceName
      })
      updateActiveSessionMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `**Recreation Plan Created for \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}`
        }
      ])
      await fetchTaasArtifacts(selectedFile)
      await fetchTaasResources()
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingResources(false)
    }
  }

  const handleEnterpriseChat = async () => {
    const text = basicChatInput.trim()
    if (!text || basicChatLoading) return
    setBasicChatInput('')
    setBasicChatLoading(true)
    setEntMessages(prev => [...prev, { role: 'user', content: text }])
    try {
      const res = await axios.post(`${API_BASE}/api/enterprise/chat`, { query: text, role: authUser.role })
      setEntMessages(prev => [...prev, { role: 'assistant', content: res.data.response || 'Done.' }])
    } catch (err) {
      setEntMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setBasicChatLoading(false)
    }
  }

  if (!authUser) {
    return (
      <div className="login-page">
        <div className="login-container">
          <div className="login-brand">
            <div className="brand-badge"><Sparkles size={24} /></div>
            <div>
              <h1>Enterprise AI & Cloud Studio</h1>
              <p>Terraform-as-a-Service • Agentic DataOps • EnterpriseGPT</p>
            </div>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              authenticate(usernameInput, passwordInput)
            }}
            className="login-form"
          >
            <div className="input-field">
              <label>Username</label>
              <div className="input-with-icon">
                <User size={17} />
                <input
                  type="text"
                  placeholder="dev, admin, or user"
                  value={usernameInput}
                  onChange={(e) => setUsernameInput(e.target.value)}
                  required
                />
              </div>
            </div>
            <div className="input-field">
              <label>Password</label>
              <div className="input-with-icon">
                <Lock size={17} />
                <input
                  type="password"
                  placeholder="Password"
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  required
                />
              </div>
            </div>
            {loginError && <div className="login-error">{loginError}</div>}
            <button type="submit" className="primary-login-btn">Continue</button>
          </form>

          <div className="quick-role-section">
            <span className="quick-role-label">Quick Role Access</span>
            <div className="role-cards-grid">
              <button type="button" className="role-demo-card" onClick={() => authenticate('dev', 'dev')}>
                <div className="role-card-top"><Terminal size={16} /><strong>Developer (TaaS + DataOps)</strong></div>
                <span className="role-cred">dev / dev</span>
              </button>
              <button type="button" className="role-demo-card" onClick={() => authenticate('admin', 'admin')}>
                <div className="role-card-top"><Briefcase size={16} /><strong>HR Portal (EnterpriseGPT)</strong></div>
                <span className="role-cred">admin / admin</span>
              </button>
              <button type="button" className="role-demo-card" onClick={() => authenticate('user', 'user')}>
                <div className="role-card-top"><User size={16} /><strong>Employee (EnterpriseGPT)</strong></div>
                <span className="role-cred">user / user</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (authUser.role === 'hr' || authUser.role === 'employee') {
    return (
      <div className="platform-shell">
        <aside className="platform-sidebar">
          <button className="new-chat-btn" onClick={() => setEntMessages([entMessages[0]])}>
            <Plus size={16} />
            <span>New Chat</span>
          </button>

          <div className="sidebar-section">
            <p className="sidebar-label">Workspace</p>
            <button className="prompt-chip-btn" onClick={() => authenticate('dev', 'dev')}>
              <Terminal size={14} /> Switch to Developer (TaaS)
            </button>
          </div>

          <div className="sidebar-footer">
            <div className="user-badge-row">
              <div className="user-avatar">{authUser.username[0].toUpperCase()}</div>
              <div className="user-meta">
                <strong>{authUser.displayName}</strong>
                <span>EnterpriseGPT</span>
              </div>
            </div>
            <button className="logout-icon-btn" onClick={() => setAuthUser(null)} title="Sign Out">
              <LogOut size={16} />
            </button>
          </div>
        </aside>

        <main className="platform-main">
          <header className="minimal-topbar">
            <span className="minimal-brand-title">EnterpriseGPT ({authUser.role.toUpperCase()})</span>
          </header>
          <div className="chat-workspace">
            <div className="messages-scroll">
              {entMessages.map((m, i) => (
                <div key={i} className={`chat-bubble-row ${m.role}`}>
                  <div className="bubble-avatar">{m.role === 'user' ? <User size={15} /> : <Sparkles size={15} />}</div>
                  <div className="bubble-card markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                </div>
              ))}
              {basicChatLoading && (
                <div className="chat-bubble-row assistant">
                  <div className="bubble-avatar"><Sparkles size={15} /></div>
                  <div className="bubble-card typing-indicator">
                    <div className="floating-spheres" aria-label="Thinking">
                      <span className="sphere" />
                      <span className="sphere" />
                      <span className="sphere" />
                    </div>
                  </div>
                </div>
              )}
            </div>
            <div className="floating-composer-wrap">
              <div className="floating-composer">
                <input
                  type="text"
                  placeholder="Message EnterpriseGPT..."
                  value={basicChatInput}
                  onChange={(e) => setBasicChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleEnterpriseChat()}
                />
                <button className="composer-send-btn" onClick={handleEnterpriseChat}>
                  <Send size={16} />
                </button>
              </div>
            </div>
          </div>
        </main>
      </div>
    )
  }

  const currentFileMeta = artifactFiles[selectedFile] || DEFAULT_STARTER_FILES[selectedFile] || {}
  const archivedTotalCount = Object.values(taasResources.deactivated || {}).reduce(
    (acc, list) => acc + (list?.length || 0),
    0
  )

  return (
    <div className="platform-shell">
      {/* LEFT SIDEBAR: New Chat + Chats & History + 1-Click TaaS */}
      <aside className="platform-sidebar">
        <button className="new-chat-btn" onClick={handleNewChat}>
          <Plus size={17} />
          <span>New chat</span>
        </button>

        <div className="sidebar-section history-section">
          <p className="sidebar-label">Chats & History</p>
          <div className="chat-history-list">
            {chatSessions.map((session) => (
              <div
                key={session.id}
                className={`history-item ${session.id === activeSessionId ? 'active' : ''}`}
                onClick={() => {
                  setActiveSessionId(session.id)
                  if (session.service) setSelectedService(session.service)
                }}
              >
                <MessageSquare size={14} className="history-icon" />
                <div className="history-text">
                  <span className="history-title">{session.title}</span>
                  <span className="history-meta">{session.createdAt}</span>
                </div>
                {chatSessions.length > 1 && (
                  <button
                    className="history-delete-btn"
                    onClick={(e) => handleDeleteChatSession(e, session.id)}
                    title="Delete chat"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {selectedService === 'taas' && (
          <div className="sidebar-section">
            <p className="sidebar-label">1-Click TaaS</p>
            <div className="prompt-chips-vertical">
              <button
                className="prompt-chip-btn"
                onClick={() =>
                  handleChatSend(
                    'Create a GCS bucket named taas-demo-raw-bkt in project solar-dialect-264808 (asia-south2) with versioning enabled'
                  )
                }
              >
                <Cloud size={14} /> GCS Bucket + Labels
              </button>
              <button
                className="prompt-chip-btn"
                onClick={() =>
                  handleChatSend(
                    'Look up official Terraform documentation for google_storage_bucket labels, lifecycle_rule, and retention_policy'
                  )
                }
              >
                <BookOpen size={14} /> Live Bucket Docs
              </button>
              <button
                className="prompt-chip-btn"
                onClick={() =>
                  handleChatSend(
                    'Create a BigQuery dataset named analytics_ds in solar-dialect-264808 (asia-south2)'
                  )
                }
              >
                <Database size={14} /> BigQuery Dataset
              </button>
              <button
                className="prompt-chip-btn"
                onClick={() =>
                  handleChatSend(
                    'Create a Pub/Sub topic named order-events-topic in solar-dialect-264808'
                  )
                }
              >
                <Server size={14} /> Pub/Sub Topic
              </button>
              <button
                className="prompt-chip-btn highlight"
                onClick={handleRunTerraformPlan}
                disabled={runningPlanOrApply}
              >
                <Play size={14} /> Run <code>terraform plan</code>
              </button>
            </div>
          </div>
        )}

        <div className="sidebar-footer">
          <div className="user-badge-row">
            <div className="user-avatar">D</div>
            <div className="user-meta">
              <strong>{authUser.displayName}</strong>
              <span>solar-dialect-264808</span>
            </div>
          </div>
          <button className="logout-icon-btn" onClick={() => setAuthUser(null)} title="Switch Role / Sign Out">
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* MAIN CANVAS AREA */}
      <main className="platform-main">
        {/* Minimal Header with Custom Rounded Service Dropdown & Sidecar Toggle */}
        <header className="minimal-topbar">
          {/* Custom Rounded Popover Dropdown (No sharp OS select corners!) */}
          <div className="custom-dropdown-container" ref={dropdownRef}>
            <button
              type="button"
              className={`custom-dropdown-trigger ${dropdownOpen ? 'open' : ''}`}
              onClick={() => setDropdownOpen(prev => !prev)}
            >
              <span className="trigger-icon-badge">
                {selectedService === 'taas' ? <Cloud size={15} /> : <Activity size={15} />}
              </span>
              <span>
                {selectedService === 'taas'
                  ? 'Terraform-as-a-Service (TaaS Studio)'
                  : 'Agentic DataOps (ServiceNow Analytics)'}
              </span>
              <ChevronDown size={15} className={`dropdown-chevron-icon ${dropdownOpen ? 'rotated' : ''}`} />
            </button>

            {dropdownOpen && (
              <div className="custom-dropdown-menu">
                <button
                  type="button"
                  className={`custom-dropdown-option ${selectedService === 'taas' ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedService('taas')
                    setDropdownOpen(false)
                  }}
                >
                  <div className="opt-icon taas"><Cloud size={18} /></div>
                  <div className="opt-text">
                    <strong>Terraform-as-a-Service</strong>
                    <span>Pre-Plan Code, Live Docs & GCP Provisioning</span>
                  </div>
                  {selectedService === 'taas' && <Check size={16} className="opt-check" />}
                </button>

                <button
                  type="button"
                  className={`custom-dropdown-option ${selectedService === 'dataops' ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedService('dataops')
                    setDropdownOpen(false)
                  }}
                >
                  <div className="opt-icon dataops"><Activity size={18} /></div>
                  <div className="opt-text">
                    <strong>Agentic DataOps</strong>
                    <span>ServiceNow Incident & MTTR Analytics</span>
                  </div>
                  {selectedService === 'dataops' && <Check size={16} className="opt-check" />}
                </button>
              </div>
            )}
          </div>

          <div className="topbar-right-controls">
            <div className="minimal-state-badge">
              <span className="dot" />
              <span>State: <code>taas/solar-dialect-264808/gcp</code></span>
            </div>

            {selectedService === 'taas' && (
              <button
                type="button"
                className={`panel-toggle-pill ${!panelCollapsed ? 'active-open' : ''}`}
                onClick={() => setPanelCollapsed(prev => !prev)}
                title={panelCollapsed ? 'Expand Pre-Plan Panel' : 'Minimize Pre-Plan Panel'}
              >
                {panelCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
                <span>{panelCollapsed ? 'Open Panel' : 'Minimize Panel'}</span>
              </button>
            )}
          </div>
        </header>

        {selectedService === 'taas' ? (
          <div
            ref={workspaceContainerRef}
            className={`taas-workspace-container ${panelCollapsed ? 'panel-collapsed' : ''} ${isDraggingPanel ? 'is-resizing' : ''}`}
          >
            {/* LEFT PANE: Chat Conversation + Approval Gate */}
            <section className="taas-chat-column">
              <div className="messages-scroll">
                {taasMessages.map((msg, idx) => (
                  <div key={idx} className={`chat-bubble-row ${msg.role}`}>
                    <div className="bubble-avatar">
                      {msg.role === 'user' ? <User size={15} /> : <Sparkles size={15} />}
                    </div>
                    <div className="bubble-card markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                ))}
                {(taasLoading || runningPlanOrApply) && (
                  <div className="chat-bubble-row assistant">
                    <div className="bubble-avatar"><Sparkles size={15} /></div>
                    <div className="bubble-card typing-indicator">
                      <div className="floating-spheres" aria-label="Thinking">
                        <span className="sphere" />
                        <span className="sphere" />
                        <span className="sphere" />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={taasChatEndRef} />
              </div>

              {pendingPlan && pendingPlan.status === 'AWAITING_APPROVAL' && (
                <div className="approval-gate-card">
                  <div className="approval-header">
                    <AlertTriangle size={17} />
                    <div>
                      <strong>Approval Gate — Plan <code>{pendingPlan.plan_id}</code></strong>
                      <p>{pendingPlan.plan_summary || 'Review the plan output above before applying to GCP.'}</p>
                    </div>
                  </div>
                  <div className="approval-controls">
                    <select
                      value={approvalDecision}
                      onChange={(e) => setApprovalDecision(e.target.value)}
                      className="approval-select"
                      disabled={runningPlanOrApply}
                    >
                      <option value="apply">apply — Approve & Provision to GCP</option>
                      <option value="dont apply">dont apply — Cancel Plan</option>
                    </select>
                    <button
                      className={`approval-confirm-btn ${approvalDecision === 'apply' ? 'approve' : 'cancel'}`}
                      onClick={handleConfirmPlanDecision}
                      disabled={runningPlanOrApply}
                    >
                      {runningPlanOrApply ? (
                        <Loader2 className="spin" size={15} />
                      ) : approvalDecision === 'apply' ? (
                        <CheckCircle2 size={15} />
                      ) : (
                        <XCircle size={15} />
                      )}
                      <span>Confirm</span>
                    </button>
                  </div>
                </div>
              )}

              <div className="floating-composer-wrap">
                <div className="floating-composer">
                  <input
                    type="text"
                    placeholder="Ask TaaS to create resources, customize HCL, or search live Terraform docs..."
                    value={taasInput}
                    onChange={(e) => setTaasInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleChatSend()}
                    disabled={taasLoading || runningPlanOrApply}
                  />
                  <button
                    className="composer-send-btn"
                    onClick={() => handleChatSend()}
                    disabled={taasLoading || runningPlanOrApply || !taasInput.trim()}
                  >
                    <Send size={16} />
                  </button>
                </div>
              </div>
            </section>

            {/* ANTIGRAVITY-STYLE CURSOR DRAG RESIZE SPLITTER */}
            {!panelCollapsed && (
              <div
                className={`antigravity-resize-splitter ${isDraggingPanel ? 'dragging' : ''}`}
                onMouseDown={(e) => {
                  e.preventDefault()
                  setIsDraggingPanel(true)
                }}
                onDoubleClick={() => setPanelWidthPct(54)}
                title="Drag left or right to resize Pre-Plan panel (Double-click to reset)"
              >
                <div className="splitter-grip-bar" />
              </div>
            )}

            {/* RIGHT PANE: ANTIGRAVITY-STYLE DRAGGABLE & MINIMIZABLE PRE-PLAN WORKBENCH PANEL */}
            <section
              className={`antigravity-side-panel ${panelCollapsed ? 'size-collapsed' : 'size-custom'} ${isDraggingPanel ? 'is-dragging' : ''}`}
              style={!panelCollapsed ? { width: `${panelWidthPct}%` } : undefined}
            >
              {panelCollapsed ? (
                /* Slim Dock Rail when Minimized */
                <div className="collapsed-sidecar-rail">
                  <button
                    className="rail-icon-btn"
                    onClick={() => setPanelCollapsed(false)}
                    title="Expand Pre-Plan Panel"
                  >
                    <PanelRightOpen size={17} />
                  </button>
                  <button
                    className={`rail-icon-btn ${taasRightTab === 'editor' ? 'active' : ''}`}
                    onClick={() => {
                      setTaasRightTab('editor')
                      setPanelCollapsed(false)
                    }}
                    title="Pre-Plan Code Editor"
                  >
                    <Code2 size={17} />
                  </button>
                  <button
                    className={`rail-icon-btn ${taasRightTab === 'docs' ? 'active' : ''}`}
                    onClick={() => {
                      setTaasRightTab('docs')
                      setPanelCollapsed(false)
                    }}
                    title="Live Terraform Docs"
                  >
                    <BookOpen size={17} />
                  </button>
                  <button
                    className={`rail-icon-btn ${taasRightTab === 'resources' ? 'active' : ''}`}
                    onClick={() => {
                      setTaasRightTab('resources')
                      setPanelCollapsed(false)
                      fetchTaasResources()
                    }}
                    title="Active Cloud Resources"
                  >
                    <Layers size={17} />
                    {(taasResources.active_count || 0) > 0 && (
                      <span className="rail-badge">{taasResources.active_count}</span>
                    )}
                  </button>
                </div>
              ) : (
                /* Full Floating Workbench Card */
                <div className="floating-workbench-card">
                  <div className="workbench-header-bar">
                    <div className="workbench-subtabs">
                      <button
                        className={`subtab-btn ${taasRightTab === 'editor' ? 'active' : ''}`}
                        onClick={() => setTaasRightTab('editor')}
                      >
                        <Code2 size={15} />
                        <span>Pre-Plan Code</span>
                      </button>
                      <button
                        className={`subtab-btn ${taasRightTab === 'docs' ? 'active' : ''}`}
                        onClick={() => setTaasRightTab('docs')}
                      >
                        <BookOpen size={15} />
                        <span>Live Docs</span>
                      </button>
                      <button
                        className={`subtab-btn ${taasRightTab === 'resources' ? 'active' : ''}`}
                        onClick={() => {
                          setTaasRightTab('resources')
                          fetchTaasResources()
                        }}
                      >
                        <Layers size={15} />
                        <span>Active Resources ({taasResources.active_count || 0})</span>
                      </button>
                    </div>

                    {/* Only Minimize Button (Width is controlled by cursor-dragging the left edge) */}
                    <div className="panel-window-controls">
                      <button
                        type="button"
                        className="win-ctrl-btn"
                        onClick={() => setPanelCollapsed(true)}
                        title="Minimize Panel"
                      >
                        <PanelRightClose size={15} />
                      </button>
                    </div>
                  </div>

                  {/* SUBTAB 1: PRE-PLAN CODE EDITOR */}
                  {taasRightTab === 'editor' && (
                    <div className="editor-pane">
                      <div className="file-tabs-bar">
                        {ARTIFACT_FILE_LIST.map((f) => {
                          const meta = artifactFiles[f.name] || DEFAULT_STARTER_FILES[f.name]
                          const isCreatedArtifact = meta?.is_artifact
                          return (
                            <button
                              key={f.name}
                              className={`file-tab-pill ${selectedFile === f.name ? 'selected' : ''}`}
                              onClick={() => handleSelectArtifactFile(f.name)}
                              title={`${f.desc} (${meta?.source_path || ''})`}
                            >
                              <FileCode size={13} />
                              <span>{f.label}</span>
                              {isCreatedArtifact && (
                                <span className="resource-dot" title="Pulled from artifacts/gcp/" />
                              )}
                            </button>
                          )
                        })}
                      </div>

                      <div className="editor-toolbar">
                        <div className="file-path-label">
                          <span className={`source-badge ${currentFileMeta.is_artifact ? 'artifact' : 'starter'}`}>
                            {currentFileMeta.is_artifact ? 'Artifact' : 'Starter'}
                          </span>
                          <code>{currentFileMeta.source_path || `terraform_starters/${selectedFile}`}</code>
                          {editorDirty && <span className="unsaved-pill">● Modified</span>}
                        </div>

                        <div className="editor-actions">
                          <button
                            className="tool-btn secondary"
                            onClick={handleLoadStarterTemplate}
                            title="Reset/Pull template from \terraform_starters"
                          >
                            <RotateCcw size={13} /> Starter
                          </button>
                          <button
                            className="tool-btn secondary"
                            onClick={() => fetchTaasArtifacts(selectedFile)}
                            title="Sync from Cloud Shell disk"
                          >
                            <RefreshCw size={13} /> Sync
                          </button>
                          <button
                            className="tool-btn primary"
                            onClick={handleSaveArtifactCode}
                            disabled={savingFile}
                          >
                            {savingFile ? <Loader2 className="spin" size={13} /> : <Save size={13} />}
                            <span>Save to Artifacts</span>
                          </button>
                          <button
                            className="tool-btn plan-btn"
                            onClick={handleRunTerraformPlan}
                            disabled={runningPlanOrApply}
                          >
                            {runningPlanOrApply ? <Loader2 className="spin" size={13} /> : <Play size={13} />}
                            <span>Plan</span>
                          </button>
                        </div>
                      </div>

                      {editorStatusMsg && <div className="editor-status-banner">{editorStatusMsg}</div>}

                      <textarea
                        className="hcl-code-textarea"
                        value={editorContent}
                        onChange={(e) => {
                          setEditorContent(e.target.value)
                          setEditorDirty(true)
                        }}
                        spellCheck={false}
                      />
                    </div>
                  )}

                  {/* SUBTAB 2: LIVE TERRAFORM DOCS */}
                  {taasRightTab === 'docs' && (
                    <div className="docs-pane">
                      <form onSubmit={handleLookupDocs} className="docs-search-bar">
                        <select
                          value={docResourceType}
                          onChange={(e) => setDocResourceType(e.target.value)}
                          className="doc-select"
                        >
                          <option value="google_storage_bucket">google_storage_bucket</option>
                          <option value="google_bigquery_dataset">google_bigquery_dataset</option>
                          <option value="google_bigquery_table">google_bigquery_table</option>
                          <option value="google_pubsub_topic">google_pubsub_topic</option>
                          <option value="google_pubsub_subscription">google_pubsub_subscription</option>
                        </select>
                        <input
                          type="text"
                          placeholder="Search attribute (labels, lifecycle_rule, retention_policy, schema)..."
                          value={docQuery}
                          onChange={(e) => setDocQuery(e.target.value)}
                        />
                        <button type="submit" className="tool-btn primary" disabled={loadingDocs}>
                          {loadingDocs ? <Loader2 className="spin" size={14} /> : <Search size={14} />}
                          <span>Search</span>
                        </button>
                      </form>

                      <div className="docs-results-scroll">
                        {!docResult ? (
                          <div className="docs-empty-state">
                            <BookOpen size={28} />
                            <h4>Live Terraform Google Provider Docs</h4>
                            <p>
                              Fetches official HashiCorp documentation in real-time (zero disk cache).
                              Search for <code>labels</code>, <code>lifecycle_rule</code>, <code>retention_policy</code>, or <code>schema</code>.
                            </p>
                          </div>
                        ) : docResult.status === 'ERROR' ? (
                          <div className="login-error">{docResult.message}</div>
                        ) : (
                          <div className="docs-result-content">
                            <div className="docs-meta-banner">
                              <span><code>{docResult.resource_type}</code></span>
                              <a href={docResult.registry_url} target="_blank" rel="noreferrer">
                                Terraform Registry ↗
                              </a>
                            </div>

                            {docResult.suggested_hcl_snippet && (
                              <div className="doc-card">
                                <div className="doc-card-header">
                                  <h5>Suggested HCL Snippet</h5>
                                  <button
                                    className="tool-btn primary"
                                    onClick={() => handleInsertSnippetToEditor(docResult.suggested_hcl_snippet)}
                                  >
                                    <PlusCircle size={13} /> Insert into Editor
                                  </button>
                                </div>
                                <pre className="code-block">{docResult.suggested_hcl_snippet}</pre>
                              </div>
                            )}

                            {docResult.matched_argument_documentation?.length > 0 && (
                              <div className="doc-card">
                                <h5>Argument Reference</h5>
                                {docResult.matched_argument_documentation.map((line, i) => (
                                  <div key={i} className="arg-doc-item markdown-body">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{line}</ReactMarkdown>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* SUBTAB 3: ENHANCED, BEAUTIFUL ACTIVE RESOURCES SHOWCASE */}
                  {taasRightTab === 'resources' && (
                    <div className="resources-pane">
                      <div className="resources-hero-banner">
                        <div className="hero-left">
                          <div className="hero-icon-circle">
                            <ShieldCheck size={20} />
                          </div>
                          <div>
                            <h4>Cloud Infrastructure Inventory</h4>
                            <p>Authoritative GCS State: <code>taas/solar-dialect-264808/gcp</code></p>
                          </div>
                        </div>
                        <button
                          className="tool-btn secondary"
                          onClick={fetchTaasResources}
                          disabled={loadingResources}
                        >
                          <RefreshCw className={loadingResources ? 'spin' : ''} size={13} /> Sync State
                        </button>
                      </div>

                      {/* 3 KPI Summary Cards */}
                      <div className="resources-summary-grid">
                        <div className="res-metric-card">
                          <div className="metric-icon active-bg"><CheckCircle2 size={17} /></div>
                          <div className="metric-info">
                            <strong>{taasResources.active_count || 0}</strong>
                            <span>Active in GCP</span>
                          </div>
                        </div>
                        <div className="res-metric-card">
                          <div className="metric-icon archived-bg"><RotateCcw size={17} /></div>
                          <div className="metric-info">
                            <strong>{archivedTotalCount}</strong>
                            <span>Deactivated</span>
                          </div>
                        </div>
                        <div className="res-metric-card">
                          <div className="metric-icon state-bg"><Cloud size={17} /></div>
                          <div className="metric-info">
                            <strong>asia-south2</strong>
                            <span>Primary Region</span>
                          </div>
                        </div>
                      </div>

                      {/* Filter & Search Bar */}
                      <div className="resources-filter-bar">
                        <div className="filter-pills-group">
                          <button
                            type="button"
                            className={`filter-pill-btn ${resourceFilter === 'all' ? 'active' : ''}`}
                            onClick={() => setResourceFilter('all')}
                          >
                            All
                          </button>
                          <button
                            type="button"
                            className={`filter-pill-btn ${resourceFilter === 'active' ? 'active' : ''}`}
                            onClick={() => setResourceFilter('active')}
                          >
                            Active ({taasResources.active_count || 0})
                          </button>
                          <button
                            type="button"
                            className={`filter-pill-btn ${resourceFilter === 'archived' ? 'active' : ''}`}
                            onClick={() => setResourceFilter('archived')}
                          >
                            Deactivated ({archivedTotalCount})
                          </button>
                        </div>

                        <div className="resource-search-input">
                          <Search size={13} />
                          <input
                            type="text"
                            placeholder="Filter resources..."
                            value={resourceSearch}
                            onChange={(e) => setResourceSearch(e.target.value)}
                          />
                        </div>
                      </div>

                      {/* Resource Category Cards */}
                      <div className="resource-groups-scroll">
                        {resourceFilter !== 'archived' &&
                          Object.entries(taasResources.active || {}).map(([category, items]) => {
                            const meta = CATEGORY_METADATA[category] || {
                              label: category.replace('_', ' ').toUpperCase(),
                              file: `${category}.tf`,
                              icon: Cloud
                            }
                            const IconComp = meta.icon
                            const filteredItems = (items || []).filter(item =>
                              !resourceSearch.trim() ||
                              item.cloud_name?.toLowerCase().includes(resourceSearch.toLowerCase()) ||
                              item.address?.toLowerCase().includes(resourceSearch.toLowerCase())
                            )

                            return (
                              <div key={category} className="resource-category-card">
                                <div className="cat-header">
                                  <div className="cat-title-wrap">
                                    <span className="cat-service-badge"><IconComp size={15} /></span>
                                    <strong>{meta.label}</strong>
                                  </div>
                                  <span className={`count-badge ${filteredItems.length === 0 ? 'zero' : ''}`}>
                                    {filteredItems.length} active
                                  </span>
                                </div>

                                {filteredItems.length === 0 ? (
                                  <p className="empty-text">No active resources deployed in <code>{meta.file}</code></p>
                                ) : (
                                  <div className="resource-list">
                                    {filteredItems.map((item, i) => (
                                      <div key={i} className="resource-row-item">
                                        <div className="res-item-left">
                                          <div className="res-top-line">
                                            <span className="live-status-dot" title="Verified Active in Google Cloud" />
                                            <span className="res-cloud-title">{item.cloud_name}</span>
                                            <code className="res-tf-chip">{meta.file}</code>
                                          </div>
                                          <span className="res-meta-line">
                                            Project: <strong>{item.project_id || 'solar-dialect-264808'}</strong>
                                            {item.dataset_id ? ` • Dataset: ${item.dataset_id}` : ''}
                                          </span>
                                        </div>
                                        <button
                                          className="deactivate-btn"
                                          onClick={() => handleDeactivateResource(category, item.tf_name)}
                                          disabled={loadingResources}
                                        >
                                          <Trash2 size={13} /> Deactivate
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )
                          })}

                        {resourceFilter !== 'active' &&
                          Object.entries(taasResources.deactivated || {}).map(([category, items]) => {
                            const filteredArchived = (items || []).filter(item =>
                              !resourceSearch.trim() ||
                              item.cloud_name?.toLowerCase().includes(resourceSearch.toLowerCase())
                            )
                            if (filteredArchived.length === 0) return null
                            const meta = CATEGORY_METADATA[category] || {
                              label: category.toUpperCase(),
                              file: `${category}.tf`,
                              icon: Layers
                            }
                            const IconComp = meta.icon
                            return (
                              <div key={`deact-${category}`} className="resource-category-card">
                                <div className="cat-header">
                                  <div className="cat-title-wrap">
                                    <span className="cat-service-badge"><IconComp size={15} /></span>
                                    <strong>{meta.label} (Archived)</strong>
                                  </div>
                                  <span className="count-badge archived">{filteredArchived.length} deactivated</span>
                                </div>
                                <div className="resource-list">
                                  {filteredArchived.map((item, i) => (
                                    <div key={i} className="resource-row-item">
                                      <div className="res-item-left">
                                        <div className="res-top-line">
                                          <span className="res-cloud-title">{item.cloud_name}</span>
                                          <code className="res-tf-chip">Commented in {meta.file}</code>
                                        </div>
                                        <span className="res-meta-line">
                                          Preserved in <code>artifacts/gcp/{meta.file}</code> for 1-click recreation
                                        </span>
                                      </div>
                                      <button
                                        className="reactivate-btn"
                                        onClick={() => handleReactivateResource(category, item.tf_name)}
                                        disabled={loadingResources}
                                      >
                                        <RotateCcw size={13} /> Recreate
                                      </button>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )
                          })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className="chat-workspace">
            <div className="messages-scroll">
              {taasMessages.map((m, i) => (
                <div key={i} className={`chat-bubble-row ${m.role}`}>
                  <div className="bubble-avatar">{m.role === 'user' ? <User size={15} /> : <Activity size={15} />}</div>
                  <div className="bubble-card markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                </div>
              ))}
              {taasLoading && (
                <div className="chat-bubble-row assistant">
                  <div className="bubble-avatar"><Activity size={15} /></div>
                  <div className="bubble-card typing-indicator">
                    <div className="floating-spheres" aria-label="Thinking">
                      <span className="sphere" />
                      <span className="sphere" />
                      <span className="sphere" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={taasChatEndRef} />
            </div>
            <div className="floating-composer-wrap">
              <div className="floating-composer">
                <input
                  type="text"
                  placeholder="Ask Agentic DataOps about ServiceNow incidents, MTTR, or backlog aging..."
                  value={taasInput}
                  onChange={(e) => setTaasInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleChatSend()}
                />
                <button className="composer-send-btn" onClick={() => handleChatSend()}>
                  <Send size={16} />
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

