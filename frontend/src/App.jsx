import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Send, User, Bot, Briefcase, Loader2, LogOut, Lock,
  Terminal, Database, Cloud, Code2, Play, CheckCircle2, XCircle, RefreshCw,
  BookOpen, Layers, AlertTriangle, Trash2, RotateCcw, Save, Sparkles,
  Server, Activity, Search, PlusCircle, FileCode, MessageSquare, Plus, ChevronDown
} from 'lucide-react'
import './App.css'

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

const INITIAL_WELCOME_MSG = {
  role: 'assistant',
  content:
    '### Welcome to Terraform-as-a-Service\n\n' +
    'Project: **`solar-dialect-264808`** • Region: **`asia-south2`** • State: **`gs://.../taas/solar-dialect-264808/gcp`**\n\n' +
    '- **Pre-Plan Code**: Starter templates from `\\terraform_starters` and created resources from `artifacts/gcp` are loaded in the editor on the right.\n' +
    '- **Customize & Plan**: Edit any `.tf` file directly or ask me in chat, then click **Run `terraform plan`**.'
}

function App() {
  // Authentication & Role State
  const [authUser, setAuthUser] = useState({
    username: 'dev',
    role: 'developer',
    displayName: 'Cloud Developer'
  })
  const [usernameInput, setUsernameInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [loginError, setLoginError] = useState('')

  // Single Service Dropdown ('taas' | 'dataops')
  const [selectedService, setSelectedService] = useState('taas')

  // ============================================================================
  // CHATS & HISTORY STATE (Left Sidebar ChatGPT/Gemini Style)
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

  // Helper to get & update current session messages
  const activeSession = chatSessions.find(s => s.id === activeSessionId) || chatSessions[0]
  const taasMessages = activeSession ? activeSession.messages : [INITIAL_WELCOME_MSG]

  const updateActiveSessionMessages = (updater) => {
    setChatSessions(prev =>
      prev.map(session => {
        if (session.id !== activeSessionId) return session
        const nextMsgs = typeof updater === 'function' ? updater(session.messages) : updater
        // Auto-title session based on first user message
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
  const [taasRightTab, setTaasRightTab] = useState('editor') // 'editor' | 'docs' | 'resources'

  // Artifact Code Editor State (artifacts/gcp/*.tf)
  const [artifactFiles, setArtifactFiles] = useState({})
  // Pre-Plan Code Editor State (Initialized with DEFAULT_STARTER_FILES so never blank!)
  const [artifactFiles, setArtifactFiles] = useState(DEFAULT_STARTER_FILES)
  const [selectedFile, setSelectedFile] = useState('bucket.tf')
  const [editorContent, setEditorContent] = useState('')
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

  const taasChatEndRef = useRef(null)

  // ============================================================================
  // 2. BASIC PLACEHOLDER STATE FOR DATAOPS & ENTERPRISE GPT
  // ============================================================================
  // Basic EnterpriseGPT State (for HR / Employee roles)
  const [basicChatInput, setBasicChatInput] = useState('')
  const [basicChatLoading, setBasicChatLoading] = useState(false)
  const [dataopsMessages, setDataopsMessages] = useState([
    {
      role: 'assistant',
      content: 'Welcome to **Agentic DataOps (Basic View)**. Ask any question about ServiceNow incidents in `solar-dialect-264808.servicenow_itsm.incidents`.'
    }
  ])
  const [entMessages, setEntMessages] = useState([
    {
      role: 'assistant',
      content: 'Welcome to **EnterpriseGPT (Basic View)**. Ask about HR bench employees, candidate resumes, or company policies.'
      content: 'Welcome to **EnterpriseGPT**. Ask about HR bench employees, candidate resumes, or company policies.'
    }
  ])

  const taasChatEndRef = useRef(null)

  useEffect(() => {
    taasChatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [taasMessages])

  useEffect(() => {
    if (authUser?.role === 'developer') {
      fetchTaasArtifacts()
      fetchTaasResources()
    }
  }, [authUser])

  // ============================================================================
  // AUTH HANDLERS
  // ============================================================================
  const authenticate = (user, pass) => {
    const u = user.trim().toLowerCase()
    const p = pass.trim()
    if (u === 'dev' && p === 'dev') {
      setAuthUser({ username: 'dev', role: 'developer', displayName: 'Cloud Infrastructure Developer' })
      setActiveDeveloperPane('taas')
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
      setLoginError('Use dev/dev (Developer - TaaS & DataOps), admin/admin (HR), or user/user (Employee).')
      setLoginError('Use dev/dev (Developer), admin/admin (HR), or user/user (Employee).')
    }
  }

  // ============================================================================
  // TAAS STUDIO HANDLERS
  // ============================================================================
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
      const files = res.data.files || {}
      setArtifactFiles(files)
      const merged = normalizeBackendFiles(res.data.files, res.data.raw_files)
      setArtifactFiles(merged)

      const targetFile = preferredFile || selectedFile
      if (files[targetFile] && !editorDirty) {
        setEditorContent(files[targetFile].content || '')
        if (merged[targetFile] && !editorDirty) {
          setEditorContent(merged[targetFile].content)
        }
        if (res.data.pending_plan && res.data.pending_plan.status === 'AWAITING_APPROVAL') {
          setPendingPlan(res.data.pending_plan)
        } else {
          setPendingPlan(null)
        }
      } catch (err) {
        console.error('Failed to load TaaS artifacts:', err)
        // Keep DEFAULT_STARTER_FILES visible even if backend is offline
        console.warn('Using starter templates fallback:', err.message)
      }
    }

  const fetchTaasResources = async () => {
      setLoadingResources(true)
      try {
        const res = await axios.get(`${API_BASE}/api/taas/resources`)
        setTaasResources(res.data)
      } catch (err) {
        console.error('Failed to load TaaS resources:', err)
        console.warn('Could not load active resources:', err.message)
      } finally {
        setLoadingResources(false)
      }
    }

    const handleSelectArtifactFile = (fileName) => {
      setSelectedFile(fileName)
      setEditorDirty(false)
      setEditorStatusMsg('')
      if (artifactFiles[fileName]) {
        setEditorContent(artifactFiles[fileName].content || '')
      } else {
        setEditorContent('')
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
        setEditorStatusMsg('Saving & running terraform fmt...')
        setEditorStatusMsg('Copying changes to artifacts/gcp & running terraform fmt...')
        try {
          const res = await axios.post(`${API_BASE}/api/taas/artifacts/update`, {
            file_name: selectedFile,
            code_content: editorContent
          })
          if (res.data.status === 'SUCCESS') {
            setEditorContent(res.data.content)
            const updatedText = res.data.content || res.data.updated_content || editorContent
            setEditorContent(updatedText)
            setEditorDirty(false)
            setEditorStatusMsg(`✓ Saved & formatted ${selectedFile} (${res.data.formatting}). Ready for terraform plan!`)
            await fetchTaasArtifacts(selectedFile)
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
        setTaasMessages(prev => [
          updateActiveSessionMessages(prev => [
            ...prev,
            { role: 'user', content: 'Run `terraform plan` on current `artifacts/gcp/` configuration.' }
      { role: 'user', content: `Run \`terraform plan\` on \`artifacts/gcp/${selectedFile}\`` }
          ])
    try {
          const res = await axios.post(`${API_BASE}/api/taas/plan`)
          const res = await axios.post(`${API_BASE}/api/taas/plan`, {
            file_name: selectedFile
          })
          const data = res.data
          if (data.status === 'AWAITING_APPROVAL') {
            setPendingPlan({
              plan_id: data.plan_id,
              const planObj = data.pending_plan || {
                plan_id: data.plan_id || data.request_id,
                request_id: data.request_id || data.plan_id,
                plan_sha256: data.plan_sha256,
                status: 'AWAITING_APPROVAL',
                plan_summary: data.plan_summary,
                active_resources: data.active_resources
              })
            setTaasMessages(prev => [
              plan_summary: data.plan_summary
        }
          setPendingPlan(planObj)
          updateActiveSessionMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content:
                `### Terraform Plan Ready (\`${data.plan_id}\`)\n\n` +
                `**Summary:** \`${data.plan_summary}\`\n\n` +
                `\`\`\`hcl\n${(data.plan_output || '').slice(-2500)}\n\`\`\`\n\n` +
                `Use the **Approval Gate** bar below to select **\`apply\`** or **\`dont apply\`**.`
                  `### Terraform Plan Ready (\`${planObj.plan_id}\`)\n\n` +
                `\`\`\`hcl\n${(data.plan_output || data.plan_summary || '').slice(-2500)}\n\`\`\`\n\n` +
                `Use the **Approval Gate** below to select **\`apply\`** or **\`dont apply\`**.`
            }
          ])
        } else {
          setTaasMessages(prev => [
            updateActiveSessionMessages(prev => [
              ...prev,
              {
                role: 'assistant',
                content: `### Terraform Plan Status: \`${data.status}\`\n\n${data.message || ''}\n\n\`\`\`\n${data.details || ''}\n\`\`\``
            content: `### Plan Status: \`${data.status}\`\n\n${data.message || ''}`
              }
            ])
      }
        await fetchTaasArtifacts()
        await fetchTaasArtifacts(selectedFile)
      } catch (err) {
        setTaasMessages(prev => [
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
      try {
        const res = await axios.post(`${API_BASE}/api/taas/approve`, {
          decision: approvalDecision,
          plan_id: pendingPlan.plan_id
        plan_id: pendingPlan.plan_id || pendingPlan.request_id,
          request_id: pendingPlan.request_id || pendingPlan.plan_id,
          plan_sha256: pendingPlan.plan_sha256
        })
        const data = res.data
        if (data.status === 'SUCCESS') {
          setTaasMessages(prev => [
            updateActiveSessionMessages(prev => [
              ...prev,
              {
                role: 'assistant',
                content:
                  `### Terraform Apply Succeeded (\`${data.plan_id}\`)\n\n` +
                  `${data.message}\n\n` +
                  `\`\`\`\n${(data.apply_output || '').slice(-2000)}\n\`\`\``
                    `*State file synced to GCS bucket.*\n\n` +
                  `\`\`\`\n${(data.apply_output || '').slice(-1800)}\n\`\`\``
              }
            ])
        setPendingPlan(null)
      } else if (data.status === 'CANCELLED') {
          setTaasMessages(prev => [
            updateActiveSessionMessages(prev => [
              ...prev,
              {
                role: 'assistant',
                content: `### Plan Cancelled (\`${data.plan_id}\`)\n\n${data.message}`
              }
            ])
        setPendingPlan(null)
      } else {
          setTaasMessages(prev => [
            updateActiveSessionMessages(prev => [
              ...prev,
              {
                role: 'assistant',
                content: `### Apply Status: \`${data.status}\`\n\n${data.message || ''}\n\n\`\`\`\n${data.details || ''}\n\`\`\``
              }
            ])
      }
        await fetchTaasArtifacts()
        await fetchTaasArtifacts(selectedFile)
        await fetchTaasResources()
      } catch (err) {
        setTaasMessages(prev => [
          updateActiveSessionMessages(prev => [
            ...prev,
            { role: 'assistant', content: `Error confirming plan decision: ${err.response?.data?.detail || err.message}` }
          ])
    } finally {
        setRunningPlanOrApply(false)
      }
    }

    const handleTaasSend = async (customPrompt = null) => {
      const handleChatSend = async (customPrompt = null) => {
        const promptText = (customPrompt ?? taasInput).trim()
        if (!promptText || taasLoading) return

        setTaasMessages(prev => [...prev, { role: 'user', content: promptText }])
        updateActiveSessionMessages(prev => [...prev, { role: 'user', content: promptText }])
        if (!customPrompt) setTaasInput('')
        setTaasLoading(true)

        // Route to either TaaS or Agentic DataOps based on the dropdown selection
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

        // TaaS Chat
        try {
          const res = await axios.post(`${API_BASE}/api/taas/chat`, {
            message: promptText
        message: promptText,
            session_id: activeSessionId
          })
          setTaasMessages(prev => [
            updateActiveSessionMessages(prev => [
              ...prev,
              { role: 'assistant', content: res.data.response || 'Completed.' }
            ])
      if (res.data.files) {
            setArtifactFiles(res.data.files)
            if (res.data.files[selectedFile] && !editorDirty) {
              setEditorContent(res.data.files[selectedFile].content || '')
            }
            const merged = normalizeBackendFiles(res.data.files, res.data.raw_files)
            setArtifactFiles(merged)

            // Auto-switch editor tab to the file modified by the agent (e.g. bucket.tf, dataset.tf)
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
            setTaasMessages(prev => [
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
          const existing = artifactFiles[destFile]?.content || ''
          const existing = artifactFiles[destFile]?.content || DEFAULT_STARTER_FILES[destFile]?.content || ''
          const combined = `${existing.trimEnd()}\n\n${snippet.trim()}\n`
          setSelectedFile(destFile)
          setEditorContent(combined)
          setEditorDirty(true)
          setTaasRightTab('editor')
          setEditorStatusMsg(`Inserted HCL snippet into ${destFile}. Review and click "Save & Format" before running plan.`)
          setEditorStatusMsg(`Inserted snippet into ${destFile}. Click "Save & Format" to update artifacts/gcp/${destFile}.`)
        }

        const handleDeactivateResource = async (category, resourceName) => {
          setLoadingResources(true)
          try {
            const res = await axios.post(`${API_BASE}/api/taas/resources/deactivate`, {
              resource_category: category,
              resource_name: resourceName
            })
            setTaasMessages(prev => [
              updateActiveSessionMessages(prev => [
                ...prev,
                {
                  role: 'assistant',
                  content: `**Deactivated \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}`
          content: `**Deactivation Plan Created for \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}`
                }
              ])
      await fetchTaasArtifacts()
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
            setTaasMessages(prev => [
              updateActiveSessionMessages(prev => [
                ...prev,
                {
                  role: 'assistant',
                  content: `**Reactivated \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}`
          content: `**Recreation Plan Created for \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}`
                }
              ])
      await fetchTaasArtifacts()
      await fetchTaasArtifacts(selectedFile)
      await fetchTaasResources()
    } catch (err) {
            console.error(err)
          } finally {
            setLoadingResources(false)
          }
        }

        // Basic Chat Handler for DataOps & EnterpriseGPT
        const handleBasicServiceChat = async (serviceType) => {
          const handleEnterpriseChat = async () => {
            const text = basicChatInput.trim()
            if (!text || basicChatLoading) return
            setBasicChatInput('')
            setBasicChatLoading(true)

            if (serviceType === 'dataops') {
              setDataopsMessages(prev => [...prev, { role: 'user', content: text }])
              try {
                const res = await axios.post(`${API_BASE}/api/dataops/chat`, { message: text })
                setDataopsMessages(prev => [...prev, { role: 'assistant', content: res.data.response || 'Done.' }])
              } catch (err) {
                setDataopsMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
              } finally {
                setBasicChatLoading(false)
              }
            } else {
              setEntMessages(prev => [...prev, { role: 'user', content: text }])
              try {
                const res = await axios.post(`${API_BASE}/api/enterprise/chat`, { query: text, role: authUser.role })
                setEntMessages(prev => [...prev, { role: 'assistant', content: res.data.response || 'Done.' }])
              } catch (err) {
                setEntMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
              } finally {
                setBasicChatLoading(false)
              }
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

            // ============================================================================
            // LOGIN SCREEN (When logged out)
            // LOGIN VIEW
            // ============================================================================
            if (!authUser) {
              return (
                <div className="login-page">
                  <div className="login-container">
                    <div className="login-brand">
                      <div className="brand-badge"><Cloud size={28} /></div>
                      <div className="brand-badge"><Sparkles size={24} /></div>
                      <div>
                        <h1>Terraform-as-a-Service & Unified AI Platform</h1>
                        <p>TaaS Studio • Agentic DataOps • EnterpriseGPT</p>
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
                          <User size={18} />
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
                          <Lock size={18} />
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
                      <button type="submit" className="primary-login-btn">Sign In</button>
                      <button type="submit" className="primary-login-btn">Continue</button>
                    </form>

                    <div className="quick-role-section">
                      <span className="quick-role-label">One-Click Role Switch</span>
                      <span className="quick-role-label">Quick Role Access</span>
                      <div className="role-cards-grid">
                        <button type="button" className="role-demo-card dev-card" onClick={() => authenticate('dev', 'dev')}>
                          <div className="role-card-top"><Terminal size={18} /><strong>Developer (TaaS + DataOps)</strong></div>
                          <button type="button" className="role-demo-card" onClick={() => authenticate('dev', 'dev')}>
                            <div className="role-card-top"><Terminal size={16} /><strong>Developer (TaaS + DataOps)</strong></div>
                            <span className="role-cred">dev / dev</span>
                          </button>
                          <button type="button" className="role-demo-card hr-card" onClick={() => authenticate('admin', 'admin')}>
                            <div className="role-card-top"><Briefcase size={18} /><strong>HR (EnterpriseGPT)</strong></div>
                            <button type="button" className="role-demo-card" onClick={() => authenticate('admin', 'admin')}>
                              <div className="role-card-top"><Briefcase size={16} /><strong>HR Portal (EnterpriseGPT)</strong></div>
                              <span className="role-cred">admin / admin</span>
                            </button>
                            <button type="button" className="role-demo-card emp-card" onClick={() => authenticate('user', 'user')}>
                              <div className="role-card-top"><User size={18} /><strong>Employee (EnterpriseGPT)</strong></div>
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

                    // ============================================================================
                    // BASIC VIEW FOR HR / EMPLOYEE (EnterpriseGPT)
                    // ============================================================================
                    if (authUser.role === 'hr' || authUser.role === 'employee') {
    return (
                    <div className="platform-shell">
                      <aside className="platform-sidebar">
                        <div className="sidebar-brand">
                          <div className="brand-icon-box"><Bot size={22} /></div>
                          <div>
                            <h2>EnterpriseGPT</h2>
                            <span className="subtitle-pill">{authUser.role.toUpperCase()} VIEW</span>
                          </div>
                        </div>
                        <button className="new-chat-btn" onClick={() => setEntMessages([entMessages[0]])}>
                          <Plus size={16} />
                          <span>New Chat</span>
                        </button>

                        <div className="sidebar-section">
                          <p className="sidebar-label">Switch Role</p>
                          <button className="nav-item-btn" onClick={() => authenticate('dev', 'dev')}>
                            <Terminal size={18} />
                            <div>
                              <strong>Switch to TaaS Studio</strong>
                              <span>Developer Console (dev/dev)</span>
                            </div>
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
                              <span>Role: {authUser.role.toUpperCase()}</span>
                              <span>EnterpriseGPT</span>
                            </div>
                          </div>
                          <button className="logout-icon-btn" onClick={() => setAuthUser(null)} title="Sign Out">
                            <LogOut size={18} />
                            <LogOut size={16} />
                          </button>
                        </div>
                      </aside>

                      <main className="platform-main">
                        <header className="main-topbar">
                          <h1>EnterpriseGPT ({authUser.displayName})</h1>
                          <header className="minimal-topbar">
                            <span className="minimal-brand-title">EnterpriseGPT ({authUser.role.toUpperCase()})</span>
                          </header>
                          <div className="chat-workspace">
                            <div className="messages-scroll">
                              {entMessages.map((m, i) => (
                                <div key={i} className={`chat-bubble-row ${m.role}`}>
                                  <div className="bubble-avatar">{m.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
                                  <div className="bubble-avatar">{m.role === 'user' ? <User size={15} /> : <Sparkles size={15} />}</div>
                                  <div className="bubble-card markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                                </div>
                              ))}
                            </div>
                            <div className="chat-composer">
                              <input
                                type="text"
                                placeholder="Ask EnterpriseGPT..."
                                value={basicChatInput}
                                onChange={(e) => setBasicChatInput(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleBasicServiceChat('enterprise')}
                              />
                              <button className="composer-send-btn" onClick={() => handleBasicServiceChat('enterprise')}>
                                <Send size={18} />
                              </button>
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

                        // ============================================================================
                        // DEVELOPER CONSOLE — FULL TERRAFORM-AS-A-SERVICE (TAAS) FRONTEND
                        // DEVELOPER WORKSPACE — CHATGPT / ENTERPRISE GEMINI FLOATING DESIGN
                        // ============================================================================
                        const currentFileMeta = artifactFiles[selectedFile] || DEFAULT_STARTER_FILES[selectedFile] || { }

                        return (
                        <div className="platform-shell developer-shell">
                          {/* Left Navigation Sidebar */}
                          <div className="platform-shell">
                            {/* LEFT SIDEBAR: New Chat + Chats & History + 1-Click TaaS */}
                            <aside className="platform-sidebar">
                              <div className="sidebar-brand">
                                <div className="brand-icon-box dev-accent">
                                  <Cloud size={22} />
                                  {/* New Chat Button */}
                                  <button className="new-chat-btn" onClick={handleNewChat}>
                                    <Plus size={17} />
                                    <span>New chat</span>
                                  </button>

                                  {/* Chats & History Section */}
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
                                    <div>
                                      <h2>TaaS Studio</h2>
                                      <span className="subtitle-pill">Terraform-as-a-Service</span>
                                    </div>
                                  </div>

                                  <div className="sidebar-section">
                                    <p className="sidebar-label">Developer Services</p>
                                    <button
                                      className={`nav-item-btn ${activeDeveloperPane === 'taas' ? 'active' : ''}`}
                                      onClick={() => setActiveDeveloperPane('taas')}
                                    >
                                      <Cloud size={18} />
                                      <div>
                                        <strong>Terraform-as-a-Service</strong>
                                        <span>Code Editor, Plan & Live Docs</span>
                                      </div>
                                    </button>

                                    <button
                                      className={`nav-item-btn ${activeDeveloperPane === 'dataops' ? 'active' : ''}`}
                                      onClick={() => setActiveDeveloperPane('dataops')}
                                    >
                                      <Activity size={18} />
                                      <div>
                                        <strong>Agentic DataOps</strong>
                                        <span>ServiceNow Analytics (Basic)</span>
                                      </div>
                                    </button>
                                  </div>

                                  {activeDeveloperPane === 'taas' && (
                                    {/* 1-Click TaaS Section (Remains in Left Sidebar) */ }
        {selectedService === 'taas' && (
                                    <div className="sidebar-section">
                                      <p className="sidebar-label">1-Click TaaS Actions</p>
                                      <p className="sidebar-label">1-Click TaaS</p>
                                      <div className="prompt-chips-vertical">
                                        <button
                                          className="prompt-chip-btn"
                                          onClick={() =>
                                            handleTaasSend(
                                              'Create a GCS bucket named taas-demo-raw-bkt in asia-south2 with versioning enabled and labels env=dev, team=dataops'
                  handleChatSend(
                                                'Create a GCS bucket named taas-demo-raw-bkt in project solar-dialect-264808 (asia-south2) with versioning enabled'
                                              )
                }
                                        >
                                          <Cloud size={14} /> Generate GCS Bucket + Labels
                                          <Cloud size={14} /> GCS Bucket + Labels
                                        </button>
                                        <button
                                          className="prompt-chip-btn"
                                          onClick={() =>
                                            handleTaasSend(
                                              'Look up official Terraform documentation for google_storage_bucket lifecycle_rule, retention_policy, and labels'
                  handleChatSend(
                                                'Look up official Terraform documentation for google_storage_bucket labels, lifecycle_rule, and retention_policy'
                                              )
                }
                                        >
                                          <BookOpen size={14} /> Lookup Bucket Docs (No Cache)
                                          <BookOpen size={14} /> Live Bucket Docs
                                        </button>
                                        <button
                                          className="prompt-chip-btn"
                                          onClick={() =>
                                            handleTaasSend(
                                              'Create a BigQuery dataset named analytics_mart in asia-south2 and a partitioned table named daily_events'
                  handleChatSend(
                                                'Create a BigQuery dataset named analytics_ds in solar-dialect-264808 (asia-south2)'
                                              )
                }
                                        >
                                          <Database size={14} /> Generate BigQuery Dataset & Table
                                          <Database size={14} /> BigQuery Dataset
                                        </button>
                                        <button
                                          className="prompt-chip-btn"
                                          onClick={() =>
                                            handleTaasSend(
                                              'Create a Pub/Sub topic named ingestion-events-topic and subscription named ingestion-events-sub'
                  handleChatSend(
                                                'Create a Pub/Sub topic named order-events-topic in solar-dialect-264808'
                                              )
                }
                                        >
                                          <Server size={14} /> Generate Pub/Sub Topic & Sub
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

                                  {/* User Footer */}
                                  <div className="sidebar-footer">
                                    <div className="user-badge-row">
                                      <div className="user-avatar dev">D</div>
                                      <div className="user-avatar">D</div>
                                      <div className="user-meta">
                                        <strong>{authUser.displayName}</strong>
                                        <span>GCP: solar-dialect-264808</span>
                                        <span>solar-dialect-264808</span>
                                      </div>
                                    </div>
                                    <button className="logout-icon-btn" onClick={() => setAuthUser(null)} title="Switch Role / Sign Out">
                                      <LogOut size={18} />
                                      <LogOut size={16} />
                                    </button>
                                  </div>
                                </aside>

                                {/* Main Workspace */}
                                {/* MAIN CANVAS AREA */}
                                <main className="platform-main">
                                  <header className="main-topbar">
                                    <div className="pane-switcher-tabs">
                                      <button
                                        className={`pane-tab ${activeDeveloperPane === 'taas' ? 'active' : ''}`}
                                        onClick={() => setActiveDeveloperPane('taas')}
                                        {/* Minimal Floating Header with Single Service Dropdown (No extra top buttons!) */}
        <header className="minimal-topbar">
                                        <div className="service-dropdown-wrapper">
                                          <Sparkles size={16} className="gemini-sparkle" />
                                          <select
                                            className="service-dropdown-select"
                                            value={selectedService}
                                            onChange={(e) => setSelectedService(e.target.value)}
                                          >
                                            <Cloud size={16} />
                                            <span>Terraform-as-a-Service (TaaS Studio)</span>
                                          </button>
                                          <button
                                            className={`pane-tab ${activeDeveloperPane === 'dataops' ? 'active' : ''}`}
                                            onClick={() => setActiveDeveloperPane('dataops')}
                                          >
                                            <Activity size={16} />
                                            <span>Agentic DataOps (Basic)</span>
                                          </button>
                                          <option value="taas">Terraform-as-a-Service (TaaS Studio)</option>
                                          <option value="dataops">Agentic DataOps (ServiceNow Analytics)</option>
                                        </select>
                                        <ChevronDown size={15} className="dropdown-chevron" />
                                    </div>

                                    <div className="topbar-right-Group">
                                      <div className="status-pill online">
                                        <span className="dot" /> State: <code>taas/solar-dialect-264808/gcp</code>
                                      </div>
                                      <div className="minimal-state-badge">
                                        <span className="dot" />
                                        <span>GCS State: <code>taas/solar-dialect-264808/gcp</code></span>
                                      </div>
                                  </header>

                                  {activeDeveloperPane === 'taas' ? (
                                    {/* WORKSPACE CONTENT */ }
        {selectedService === 'taas' ? (
                                    <div className="taas-split-layout">
                                      {/* LEFT COLUMN: Conversational TaaS Agent + Mandatory Approval Gate */}
                                      {/* LEFT PANE: Floating Gemini/ChatGPT Conversation + Approval Gate */}
                                      <section className="taas-chat-column">
                                        <div className="column-header">
                                          <div className="header-title-group">
                                            <Sparkles size={18} className="accent-icon" />
                                            <h3>TaaS Infrastructure Agent</h3>
                                          </div>
                                          <span className="badge-tag">Live Docs + Pre-Plan Edit</span>
                                        </div>

                                        <div className="messages-scroll compact">
                                          <div className="messages-scroll">
                                            {taasMessages.map((msg, idx) => (
                                              <div key={idx} className={`chat-bubble-row ${msg.role}`}>
                                                <div className="bubble-avatar">
                                                  {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                                                  {msg.role === 'user' ? <User size={15} /> : <Sparkles size={15} />}
                                                </div>
                                                <div className="bubble-card markdown-body">
                                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                                                </div>
                                              </div>
                                            ))}
                                            {(taasLoading || runningPlanOrApply) && (
                                              <div className="chat-bubble-row assistant">
                                                <div className="bubble-avatar"><Bot size={16} /></div>
                                                <div className="bubble-avatar"><Sparkles size={15} /></div>
                                                <div className="bubble-card typing-indicator">
                                                  <Loader2 className="spin" size={16} />
                                                  <Loader2 className="spin" size={15} />
                                                  <span>
                                                    {runningPlanOrApply
                                                      ? 'Running Terraform CLI (init / validate / plan / apply)...'
                                                      : 'TaaS Agent is generating HCL & checking documentation...'}
                                                    ? 'Executing Terraform CLI against GCS state...'
                          : 'Generating Terraform configuration...'}
                                                  </span>
                                                </div>
                                              </div>
                                            )}
                                            <div ref={taasChatEndRef} />
                                          </div>

                                          {/* Mandatory Plan Approval Gate Card */}
                                          {/* Floating Approval Gate Card */}
                                          {pendingPlan && pendingPlan.status === 'AWAITING_APPROVAL' && (
                                            <div className="approval-gate-card">
                                              <div className="approval-header">
                                                <AlertTriangle size={18} />
                                                <AlertTriangle size={17} />
                                                <div>
                                                  <strong>Approval Gate — Plan <code>{pendingPlan.plan_id}</code></strong>
                                                  <p>{pendingPlan.plan_summary || 'Review the plan output above before applying.'}</p>
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
                        <Loader2 className="spin" size={16} />
                        <Loader2 className="spin" size={15} />
                                                  ) : approvalDecision === 'apply' ? (
                        <CheckCircle2 size={16} />
                        <CheckCircle2 size={15} />
                                                  ) : (
                        <XCircle size={16} />
                        <XCircle size={15} />
                                                  )}
                                                  <span>Confirm ({approvalDecision})</span>
                                                  <span>Confirm</span>
                                                </button>
                                              </div>
                                            </div>
                                          )}

                                          <div className="chat-composer">
                                            <input
                                              type="text"
                                              placeholder="Describe the GCP infrastructure or customization you need (e.g., 'Add retention_policy to my bucket')..."
                                              value={taasInput}
                                              onChange={(e) => setTaasInput(e.target.value)}
                                              onKeyDown={(e) => e.key === 'Enter' && handleTaasSend()}
                                              disabled={taasLoading || runningPlanOrApply}
                                            />
                                            <button
                                              className="composer-send-btn"
                                              onClick={() => handleTaasSend()}
                                              disabled={taasLoading || runningPlanOrApply || !taasInput.trim()}
                                            >
                                              <Send size={18} />
                                            </button>
                                            {/* Floating Pill Composer (ChatGPT / Gemini Style) */}
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

                                          {/* RIGHT COLUMN: Pre-Plan Code Editor, Live Docs Lookup, Active Cloud Inventory */}
                                          {/* RIGHT PANE: Floating Pre-Plan Code Card (Starters + Artifacts), Live Docs & Resources */}
                                          <section className="taas-workbench-column">
                                            <div className="workbench-subtabs">
                                              <button
                                                className={`subtab-btn ${taasRightTab === 'editor' ? 'active' : ''}`}
                                                onClick={() => setTaasRightTab('editor')}
                                              >
                                                <Code2 size={16} />
                                                <span>1. Pre-Plan Code Editor (<code>artifacts/gcp/</code>)</span>
                                              </button>
                                              <button
                                                className={`subtab-btn ${taasRightTab === 'docs' ? 'active' : ''}`}
                                                onClick={() => setTaasRightTab('docs')}
                                              >
                                                <BookOpen size={16} />
                                                <span>2. Live Terraform Docs (Zero Cache)</span>
                                              </button>
                                              <button
                                                className={`subtab-btn ${taasRightTab === 'resources' ? 'active' : ''}`}
                                                onClick={() => {
                                                  setTaasRightTab('resources')
                                                  fetchTaasResources()
                                                }}
                                              >
                                                <Layers size={16} />
                                                <span>3. Active Resources ({taasResources.active_count || 0})</span>
                                              </button>
                                            </div>
                                            <div className="floating-workbench-card">
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

                                              {/* SUBTAB 1: PRE-PLAN ARTIFACT CODE EDITOR */}
                                              {taasRightTab === 'editor' && (
                                                <div className="editor-pane">
                                                  <div className="file-tabs-bar">
                                                    {ARTIFACT_FILE_LIST.map((f) => {
                                                      const hasRes = artifactFiles[f.name]?.has_resources
                                                      return (
                                                        {/* SUBTAB 1: PRE-PLAN CODE EDITOR (terraform_starters + artifacts/gcp) */ }
                {
                                                        taasRightTab === 'editor' && (
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
                                                                  key={f.name}
                                                                  className={`file-tab-pill ${selectedFile === f.name ? 'selected' : ''} ${hasRes ? 'populated' : ''}`}
                                                                  onClick={() => handleSelectArtifactFile(f.name)}
                                                                  title={f.desc}
                                                                  className="tool-btn secondary"
                                                                  onClick={handleLoadStarterTemplate}
                                                                  title="Reset/Pull template from \terraform_starters"
                                                                >
                                                                  <FileCode size={13} />
                                                                  <span>{f.label}</span>
                                                                  {hasRes && <span className="resource-dot" title="Contains active Terraform resources" />}
                                                                  <RotateCcw size={13} /> Starter
                                                                </button>
                                                                )
                    })}
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
                                                        )
                                                      }

                                                      <div className="editor-toolbar">
                                                        <span className="file-path-label">
                                                          <code>artifacts/gcp/{selectedFile}</code>
                                                          {editorDirty && <span className="unsaved-pill">● Unsaved Pre-Plan Edits</span>}
                                                        </span>
                                                        <div className="editor-actions">
                                                          <button
                                                            className="tool-btn secondary"
                                                            onClick={() => fetchTaasArtifacts(selectedFile)}
                                                            title="Reload from disk"
                                                            {/* SUBTAB 2: LIVE TERRAFORM DOCS (ZERO CACHE) */}
                                                            {taasRightTab === 'docs' && (
                                                              <div className="docs-pane">
                                                                <form onSubmit={handleLookupDocs} className="docs-search-bar">
                                                                  <select
                                                                    value={docResourceType}
                                                                    onChange={(e) => setDocResourceType(e.target.value)}
                                                                    className="doc-select"
                                                                  >
                                                                    <RefreshCw size={14} /> Reload
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
                                                                  <button
                                                                    className="tool-btn primary"
                                                                    onClick={handleSaveArtifactCode}
                                                                    disabled={savingFile}
                                                                  >
                                                                    {savingFile ? <Loader2 className="spin" size={14} /> : <Save size={14} />}
                                                                    <span>Save & Format (<code>terraform fmt</code>)</span>
                                                                  </button>
                                                                  <button
                                                                    className="tool-btn plan-btn"
                                                                    onClick={handleRunTerraformPlan}
                                                                    disabled={runningPlanOrApply}
                                                                  >
                                                                    {runningPlanOrApply ? <Loader2 className="spin" size={14} /> : <Play size={14} />}
                                                                    <span>Run <code>terraform plan</code></span>
                                                                  </button>
                                                              </div>
                  </div>
                                                      </form>

                                                      { editorStatusMsg && <div className="editor-status-banner">{editorStatusMsg}</div> }

                                                      <textarea
                                                        className="hcl-code-textarea"
                                                        value={editorContent}
                                                        onChange={(e) => {
                                                          setEditorContent(e.target.value)
                                                          setEditorDirty(true)
                                                        }}
                                                        spellCheck={false}
                                                        placeholder="# Select or generate a Terraform (.tf) file to inspect and customize before running terraform plan..."
                                                      />
                </div>
              )}

                                                  {/* SUBTAB 2: LIVE TERRAFORM PROVIDER DOCS LOOKUP (NO CACHE) */}
                                                  {taasRightTab === 'docs' && (
                                                    <div className="docs-pane">
                                                      <form onSubmit={handleLookupDocs} className="docs-search-bar">
                                                        <select
                                                          value={docResourceType}
                                                          onChange={(e) => setDocResourceType(e.target.value)}
                                                          className="doc-select"
                                                        >
                                                          <option value="google_storage_bucket">google_storage_bucket (GCS Bucket)</option>
                                                          <option value="google_bigquery_dataset">google_bigquery_dataset (BigQuery Dataset)</option>
                                                          <option value="google_bigquery_table">google_bigquery_table (BigQuery Table)</option>
                                                          <option value="google_pubsub_topic">google_pubsub_topic (Pub/Sub Topic)</option>
                                                          <option value="google_pubsub_subscription">google_pubsub_subscription (Pub/Sub Subscription)</option>
                                                        </select>
                                                        <input
                                                          type="text"
                                                          placeholder="Search attribute (e.g. labels, lifecycle_rule, retention_policy, schema)..."
                                                          value={docQuery}
                                                          onChange={(e) => setDocQuery(e.target.value)}
                                                        />
                                                        <button type="submit" className="tool-btn primary" disabled={loadingDocs}>
                                                          {loadingDocs ? <Loader2 className="spin" size={14} /> : <Search size={14} />}
                                                          <span>Fetch Live Docs</span>
                                                        </button>
                                                      </form>

                                                      <div className="docs-results-scroll">
                                                        {!docResult ? (
                                                          <div className="docs-empty-state">
                                                            <BookOpen size={32} />
                                                            <h4>Real-Time Terraform Google Provider Docs (Zero Disk Cache)</h4>
                                                            <p>
                                                              Queries the official HashiCorp <code>terraform-provider-google</code> documentation live over HTTPS.
                                                              Search for keywords like <code>labels</code>, <code>tags</code>, <code>lifecycle_rule</code>,{' '}
                                                              <code>retention_policy</code>, or <code>time_partitioning</code>.
                                                            </p>
                                                          </div>
                                                        ) : docResult.status === 'ERROR' ? (
                                                          <div className="login-error">{docResult.message}</div>
                                                        ) : (
                                                          <div className="docs-result-content">
                                                            <div className="docs-meta-banner">
                                                              <span>Resource: <code>{docResult.resource_type}</code> (Fetched Live)</span>
                                                              <a href={docResult.registry_url} target="_blank" rel="noreferrer">
                                                                Open Terraform Registry ↗
                                                              </a>
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

                        {docResult.suggested_hcl_snippet && (
                                                                  <div className="doc-card">
                                                                    <div className="doc-card-header">
                                                                      <h5>Suggested HCL Code Pattern</h5>
                                                                      <button
                                                                        className="tool-btn primary"
                                                                        onClick={() => handleInsertSnippetToEditor(docResult.suggested_hcl_snippet)}
                                                                      >
                                                                        <PlusCircle size={14} /> Insert into Code Editor
                                                                      </button>
                                                                    </div>
                                                                    <pre className="code-block">{docResult.suggested_hcl_snippet}</pre>
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
                        )}

                                                                      {docResult.matched_argument_documentation?.length > 0 && (
                                                                        <div className="doc-card">
                                                                          <h5>Matched Argument Reference (Live from Upstream Docs)</h5>
                                                                          {docResult.matched_argument_documentation.map((line, i) => (
                                                                            <div key={i} className="arg-doc-item markdown-body">
                                                                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{line}</ReactMarkdown>
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
                            ))}
                                                                                </div>
                                                                              )}
                                                                              <pre className="code-block">{docResult.suggested_hcl_snippet}</pre>
                                                                            </div>
                                                                          )}

                                                                          {docResult.official_hcl_examples?.length > 0 && (
                                                                            <div className="doc-card">
                                                                              <h5>Official Upstream HCL Examples</h5>
                                                                              {docResult.official_hcl_examples.map((ex, i) => (
                                                                                <div key={i} className="example-block-wrapper">
                                                                                  <div className="doc-card-header">
                                                                                    <span>Example #{i + 1}</span>
                                                                                    <button
                                                                                      className="tool-btn secondary"
                                                                                      onClick={() => handleInsertSnippetToEditor(ex)}
                                                                                    >
                                                                                      <PlusCircle size={13} /> Insert Example into Editor
                                                                                    </button>
                                                                                    {docResult.matched_argument_documentation?.length > 0 && (
                                                                                      <div className="doc-card">
                                                                                        <h5>Argument Reference</h5>
                                                                                        {docResult.matched_argument_documentation.map((line, i) => (
                                <div key={i} className="arg-doc-item markdown-body">
                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{line}</ReactMarkdown>
                                </div>
                                <pre className="code-block">{ex}</pre>
                              </div>
                                                                                    ))}
                                                                                  </div>
                        )}
                                                                                </div>
                                                                              )}
                                                                            </div>
                </div>
                                                                      )}

                                                                      {/* SUBTAB 3: ACTIVE & DEACTIVATED CLOUD RESOURCES */}
                                                                      {taasRightTab === 'resources' && (
                <div className="resources-pane">
                  <div className="pane-Section-header">
                    <div>
                      <h4>Active Provisioned Infrastructure</h4>
                      <p>Managed in single state <code>taas/solar-dialect-264808/gcp</code></p>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    <button className="tool-btn secondary" onClick={fetchTaasResources} disabled={loadingResources}>
                      <RefreshCw className={loadingResources ? 'spin' : ''} size={14} /> Refresh
                    </button>
                  </div>
                )}

                                                                    <div className="resource-groups-scroll">
                                                                      {Object.entries(taasResources.active || {}).map(([category, items]) => (
                                                                        <div key={category} className="resource-category-card">
                                                                          <div className="cat-header">
                                                                            <strong>{category.replace('_', ' ').toUpperCase()}</strong>
                                                                            <span className="count-badge">{items.length} active</span>
                                                                          </div>
                                                                          {items.length === 0 ? (
                                                                            <p className="empty-text">No active resources in {category}.tf</p>
                                                                          ) : (
                                                                            <div className="resource-list">
                                                                              {items.map((item, i) => (
                                                                                <div key={i} className="resource-row-item">
                                                                                  <div>
                                                                                    <code>{item.address}</code>
                                                                                    <span className="res-name-sub">Cloud Name: <strong>{item.cloud_name}</strong></span>
                                                                                  </div>
                                                                                  <button
                                                                                    className="deactivate-btn"
                                                                                    onClick={() => handleDeactivateResource(category, item.tf_name)}
                                                                                    disabled={loadingResources}
                                                                                  >
                                                                                    <Trash2 size={14} /> Deactivate
                                                                                  </button>
                                                                                </div>
                                                                              ))}
                                                                            </div>
                                                                          )}
                                                                        </div>
                                                                      ))}

                                                                      <div className="pane-Section-header" style={{ marginTop: '1.25rem' }}>
                                                                        {/* SUBTAB 3: ACTIVE & DEACTIVATED CLOUD RESOURCES */}
                                                                        {taasRightTab === 'resources' && (
                                                                          <div className="resources-pane">
                                                                            <div className="pane-Section-header">
                                                                              <div>
                                                                                <h4>Deactivated History (One-Click Recreate)</h4>
                                                                                <p>Previously destroyed resources archived in <code>deactivated_resources.json</code></p>
                                                                                <h4>Provisioned Cloud Resources</h4>
                                                                                <p>State synced in GCS bucket (<code>taas/solar-dialect-264808/gcp</code>)</p>
                                                                              </div>
                                                                              <button className="tool-btn secondary" onClick={fetchTaasResources} disabled={loadingResources}>
                                                                                <RefreshCw className={loadingResources ? 'spin' : ''} size={13} /> Refresh
                                                                              </button>
                                                                            </div>

                                                                            {Object.entries(taasResources.deactivated || {}).map(([category, items]) =>
                                                                              items.length > 0 ? (
                                                                                <div key={`deact-${category}`} className="resource-category-card deactivated">
                                                                                  <div className="resource-groups-scroll">
                                                                                    {Object.entries(taasResources.active || {}).map(([category, items]) => (
                                                                                      <div key={category} className="resource-category-card">
                                                                                        <div className="cat-header">
                                                                                          <strong>{category.toUpperCase()} (Deactivated)</strong>
                                                                                          <span className="count-badge">{items.length} archived</span>
                                                                                          <strong>{category.replace('_', ' ').toUpperCase()}</strong>
                                                                                          <span className="count-badge">{items.length} active</span>
                                                                                        </div>
                                                                                        <div className="resource-list">
                                                                                          {items.map((item, i) => (
                                                                                            <div key={i} className="resource-row-item">
                                                                                              <div>
                                                                                                <code>{item.address}</code>
                                                                                                <span className="res-name-sub">Destroyed at: {item.deactivated_at}</span>
                                                                                                {items.length === 0 ? (
                                                                                                  <p className="empty-text">No active resources</p>
                                                                                                ) : (
                                                                                                  <div className="resource-list">
                                                                                                    {items.map((item, i) => (
                                <div key={i} className="resource-row-item">
                                  <div>
                                    <code>{item.address}</code>
                                    <span className="res-name-sub">Name: <strong>{item.cloud_name}</strong></span>
                                  </div>
                                  <button
                                    className="deactivate-btn"
                                    onClick={() => handleDeactivateResource(category, item.tf_name)}
                                    disabled={loadingResources}
                                  >
                                    <Trash2 size={13} /> Deactivate
                                  </button>
                                </div>
                                <button
                                  className="reactivate-btn"
                                  onClick={() => handleReactivateResource(category, item.tf_name)}
                                  disabled={loadingResources}
                                >
                                  <RotateCcw size={14} /> Recreate
                                </button>
                              </div>
                                                                                                ))}
                              ))}
                                                                                              </div>
                          )}
                                                                                            </div>
                                                                                          ))}

                                                                                          {Object.entries(taasResources.deactivated || {}).map(([category, items]) =>
                                                                                            items.length > 0 ? (
                                                                                              <div key={`deact-${category}`} className="resource-category-card deactivated">
                                                                                                <div className="cat-header">
                                                                                                  <strong>{category.toUpperCase()} (Deactivated)</strong>
                                                                                                  <span className="count-badge">{items.length} archived</span>
                                                                                                </div>
                                                                                                <div className="resource-list">
                                                                                                  {items.map((item, i) => (
                                                                                                    <div key={i} className="resource-row-item">
                                                                                                      <div>
                                                                                                        <code>{item.address}</code>
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
                        </div>
                                                                                        ) : null
                    )}
                                                                                        ) : null
                      )}
                                                                                      </div>
                  </div>
                                                                                </div>
                                                                              )}
                )}
                                                                          </div>
            </section>
                                                                    </div>
                                                                    ) : (
                                                                    /* BASIC VIEW FOR AGENTIC DATAOPS */
                                                                    /* BASIC VIEW FOR AGENTIC DATAOPS (Selected via Dropdown) */
                                                                    <div className="chat-workspace">
                                                                      <div className="messages-scroll">
                                                                        {dataopsMessages.map((m, i) => (
                                                                          {
                                                                            taasMessages.map((m, i) => (
                                                                              <div key={i} className={`chat-bubble-row ${m.role}`}>
                                                                                <div className="bubble-avatar">{m.role === 'user' ? <User size={16} /> : <Bot size={16} />}</div>
                                                                                <div className="bubble-avatar">{m.role === 'user' ? <User size={15} /> : <Activity size={15} />}</div>
                                                                                <div className="bubble-card markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                                                                              </div>
                                                                            ))
                                                                          }
              { taasLoading && (
                                                                            <div className="chat-bubble-row assistant">
                                                                              <div className="bubble-avatar"><Activity size={15} /></div>
                                                                              <div className="bubble-card typing-indicator">
                                                                                <Loader2 className="spin" size={15} />
                                                                                <span>Querying ServiceNow incidents in BigQuery...</span>
                                                                              </div>
                                                                            </div>
                                                                          )}
                                                                        <div ref={taasChatEndRef} />
                                                                      </div>
                                                                      <div className="chat-composer">
                                                                        <input
                                                                          type="text"
                                                                          placeholder="Ask Agentic DataOps about ServiceNow incidents..."
                                                                          value={basicChatInput}
                                                                          onChange={(e) => setBasicChatInput(e.target.value)}
                                                                          onKeyDown={(e) => e.key === 'Enter' && handleBasicServiceChat('dataops')}
                                                                        />
                                                                        <button className="composer-send-btn" onClick={() => handleBasicServiceChat('dataops')}>
                                                                          <Send size={18} />
                                                                        </button>
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

                                                                export default App
