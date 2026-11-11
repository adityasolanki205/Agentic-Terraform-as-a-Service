import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Send, User, Briefcase, Loader2, LogOut, Lock,
  Terminal, Database, Cloud, Code2, Play, CheckCircle2, XCircle, RefreshCw,
  Layers, AlertTriangle, Trash2, RotateCcw, Save, Sparkles,
  Server, Activity, Search, FileCode, MessageSquare, Plus,
  ChevronDown, ChevronRight, PanelRightClose, PanelRightOpen, Check, ShieldCheck,
  HardDrive
} from 'lucide-react'
import './StudioLight.css'


const DEFAULT_STARTER_FILES = {
  'bucket.tf': {
    content: `# Google Cloud Storage bucket resource template.
resource "google_storage_bucket" "requested" {
  name                        = var.resource_config["bucket_name"]
  project                     = var.project_id
  location                    = var.location
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = lookup(var.resource_config, "versioning", false)
  }
}`,
    starter_content: `# Google Cloud Storage bucket resource template.
resource "google_storage_bucket" "requested" {
  name                        = var.resource_config["bucket_name"]
  project                     = var.project_id
  location                    = var.location
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = lookup(var.resource_config, "versioning", false)
  }
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/storage_bucket/bucket.tf',
    is_artifact: false
  },
  'dataset.tf': {
    content: `# BigQuery dataset resource template.
resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.resource_config["dataset_id"]
  location   = var.location
}`,
    starter_content: `# BigQuery dataset resource template.
resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.resource_config["dataset_id"]
  location   = var.location
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/bigquery_dataset/dataset.tf',
    is_artifact: false
  },
  'table.tf': {
    content: `# BigQuery table resource template.
resource "google_bigquery_table" "requested" {
  project             = var.project_id
  dataset_id          = var.resource_config["dataset_id"]
  table_id            = var.resource_config["table_id"]
  deletion_protection = false
  schema              = lookup(var.resource_config, "schema", null)
}`,
    starter_content: `# BigQuery table resource template.
resource "google_bigquery_table" "requested" {
  project             = var.project_id
  dataset_id          = var.resource_config["dataset_id"]
  table_id            = var.resource_config["table_id"]
  deletion_protection = false
  schema              = lookup(var.resource_config, "schema", null)
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/bigquery_table/table.tf',
    is_artifact: false
  },
  'topic.tf': {
    content: `# Google Cloud Pub/Sub topic resource template.
resource "google_pubsub_topic" "requested" {
  name    = var.resource_config["topic_name"]
  project = var.project_id
}`,
    starter_content: `# Google Cloud Pub/Sub topic resource template.
resource "google_pubsub_topic" "requested" {
  name    = var.resource_config["topic_name"]
  project = var.project_id
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/gcp/pubsub_topic/topic.tf',
    is_artifact: false
  },
  'subscription.tf': {
    content: `# Google Cloud Pub/Sub subscription resource template.
resource "google_pubsub_subscription" "requested" {
  name                       = var.resource_config["subscription_name"]
  topic                      = var.resource_config["topic"]
  project                    = var.project_id
  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 20
}`,
    starter_content: `# Google Cloud Pub/Sub subscription resource template.
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
    is_artifact: false
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
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/common/main.tf',
    is_artifact: false
  },
  'variables.tf': {
    content: `variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "location" {
  description = "Google Cloud default location."
  type        = string
  default     = "asia-south2"
}`,
    starter_content: `variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "location" {
  description = "Google Cloud default location."
  type        = string
  default     = "asia-south2"
}`,
    source: 'terraform_starters',
    source_path: 'terraform_starters/common/variables.tf',
    is_artifact: false
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



// 1-Click TaaS Umbrella Resource Catalog (Only Available Resources in terraform_starters/gcp)
const TAAS_UMBRELLA_CATALOG = [
  {
    id: 'data',
    label: 'Data',
    icon: Database,
    items: [
      {
        id: 'bigquery_dataset',
        label: 'BigQuery Dataset',
        defaultFile: 'dataset.tf',
        userTrigger: 'Create a BigQuery Dataset',
        assistantAsk:
          'What would you like the **BigQuery Dataset** to be named, and which **region** do you want to create it in (e.g., `asia-south2`)?',
        buildAgentPrompt: (reply) =>
          `Create a BigQuery dataset in project solar-dialect-264808 with these details: ${reply} (default region asia-south2 if not specified). Update dataset.tf and run the Terraform plan.`
      },
      {
        id: 'bigquery_table',
        label: 'BigQuery Table',
        defaultFile: 'table.tf',
        userTrigger: 'Create a BigQuery Table',
        assistantAsk:
          'What would you like the **BigQuery Table** to be named, which **Dataset ID** should it be created in, and which **region** do you want to use (e.g., `asia-south2`)?',
        buildAgentPrompt: (reply) =>
          `Create a BigQuery table in project solar-dialect-264808 with these details: ${reply} (default region asia-south2 if not specified). Update table.tf and run the Terraform plan.`
      }
    ]
  },
  {
    id: 'storage',
    label: 'Storage',
    icon: HardDrive,
    items: [
      {
        id: 'storage_bucket',
        label: 'Cloud Storage Bucket',
        defaultFile: 'bucket.tf',
        userTrigger: 'Create a Cloud Storage Bucket',
        assistantAsk:
          'What would you like the **Cloud Storage Bucket** to be named, and which **region** do you want to create it in (e.g., `asia-south2`)?',
        buildAgentPrompt: (reply) =>
          `Create a GCS storage bucket in project solar-dialect-264808 with these details: ${reply} (default region asia-south2 if not specified). Update bucket.tf and run the Terraform plan.`
      }
    ]
  },
  {
    id: 'messaging',
    label: 'Messaging',
    icon: Server,
    items: [
      {
        id: 'pubsub_topic',
        label: 'Pub/Sub Topic',
        defaultFile: 'topic.tf',
        userTrigger: 'Create a Pub/Sub Topic',
        assistantAsk:
          'What would you like the **Pub/Sub Topic** to be named, and which **region** do you want to create it in (e.g., `asia-south2`)?',
        buildAgentPrompt: (reply) =>
          `Create a Pub/Sub topic in project solar-dialect-264808 with these details: ${reply}. Update topic.tf and run the Terraform plan.`
      },
      {
        id: 'pubsub_subscription',
        label: 'Pub/Sub Subscription',
        defaultFile: 'subscription.tf',
        userTrigger: 'Create a Pub/Sub Subscription',
        assistantAsk:
          'What would you like the **Pub/Sub Subscription** to be named, which **Pub/Sub Topic** should it attach to, and in which **region**?',
        buildAgentPrompt: (reply) =>
          `Create a Pub/Sub subscription in project solar-dialect-264808 with these details: ${reply}. Update subscription.tf and run the Terraform plan.`
      }
    ]
  }
]

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function ThinkingSpheres() {
  return (
    <div className="floating-spheres" aria-label="Thinking">
      <span className="sphere" />
      <span className="sphere" />
      <span className="sphere" />
    </div>
  )
}

export default function StudioApp() {
  // 1. Auth & Service State
  const [authUser, setAuthUser] = useState({
    username: 'dev',
    role: 'developer',
    displayName: 'Cloud Developer'
  })
  const [usernameInput, setUsernameInput] = useState('')
  const [passwordInput, setPasswordInput] = useState('')
  const [loginError, setLoginError] = useState('')
  const [selectedService, setSelectedService] = useState('taas')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef(null)

  // 2. Right Panel State (Minimize + Cursor Drag Width)
  const [panelCollapsed, setPanelCollapsed] = useState(false)
  const [panelWidthPct, setPanelWidthPct] = useState(54)
  const [isDraggingPanel, setIsDraggingPanel] = useState(false)
  const workspaceContainerRef = useRef(null)
  const [taasRightTab, setTaasRightTab] = useState('editor')

  // 3. Chat Sessions State (Starts empty so chat opens in the middle like Gemini)
  const [chatSessions, setChatSessions] = useState([
    { id: 'session-1', title: 'New Infrastructure Chat', service: 'taas', createdAt: 'Just now', messages: [] }
  ])
  const [activeSessionId, setActiveSessionId] = useState('session-1')
  const [taasInput, setTaasInput] = useState('')
  const [taasLoading, setTaasLoading] = useState(false)
  const taasChatEndRef = useRef(null)

  const activeSession = chatSessions.find((s) => s.id === activeSessionId) || chatSessions[0]
  const taasMessages = activeSession ? activeSession.messages : []

  // 4. Pre-Plan Editor, Approval Gate, Docs & Resources State
  const [artifactFiles, setArtifactFiles] = useState(DEFAULT_STARTER_FILES)
  const [selectedFile, setSelectedFile] = useState('bucket.tf')
  const [editorContent, setEditorContent] = useState(DEFAULT_STARTER_FILES['bucket.tf'].content)
  const [editorDirty, setEditorDirty] = useState(false)
  const [savingFile, setSavingFile] = useState(false)
  const [editorStatusMsg, setEditorStatusMsg] = useState('')

  const [pendingPlan, setPendingPlan] = useState(null)
  const [approvalDecision, setApprovalDecision] = useState('apply')
  const [runningPlanOrApply, setRunningPlanOrApply] = useState(false)

  const [taasResources, setTaasResources] = useState({ active: {}, deactivated: {}, active_count: 0 })
  const [loadingResources, setLoadingResources] = useState(false)
  const [resourceFilter, setResourceFilter] = useState('all')
  const [resourceSearch, setResourceSearch] = useState('')

  // 1-Click TaaS Umbrella Accordion & Chat Follow-up State
  const [openUmbrella, setOpenUmbrella] = useState('data')
  const [pendingOneClickItem, setPendingOneClickItem] = useState(null)

  // 5. EnterpriseGPT State (for HR / Employee roles)
  const [basicChatInput, setBasicChatInput] = useState('')
  const [basicChatLoading, setBasicChatLoading] = useState(false)
  const [entMessages, setEntMessages] = useState([])

  // Close service dropdown on outside click
  useEffect(() => {
    const onDocClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  // Cursor-drag resize handler for right sidecar panel
  useEffect(() => {
    if (!isDraggingPanel) return
    const onMove = (e) => {
      const box = workspaceContainerRef.current?.getBoundingClientRect()
      if (!box || box.width <= 0) return
      const pct = ((box.right - e.clientX) / box.width) * 100
      setPanelWidthPct(Math.min(76, Math.max(26, pct)))
    }
    const onUp = () => {
      setIsDraggingPanel(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
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

  const updateActiveSessionMessages = (updater) => {
    setChatSessions((prev) =>
      prev.map((s) => {
        if (s.id !== activeSessionId) return s
        const nextMsgs = typeof updater === 'function' ? updater(s.messages) : updater
        const firstUser = nextMsgs.find((m) => m.role === 'user')
        const title = firstUser
          ? firstUser.content.slice(0, 34) + (firstUser.content.length > 34 ? '...' : '')
          : s.title
        return { ...s, messages: nextMsgs, title }
      })
    )
  }

  const handleNewChat = () => {
    const newId = `session-${Date.now()}`
    const newSession = {
      id: newId,
      title: selectedService === 'dataops' ? 'New DataOps Query' : 'New Infrastructure Chat',
      service: selectedService,
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      messages: []
    }
    setChatSessions((prev) => [newSession, ...prev])
    setActiveSessionId(newId)
    setPendingOneClickItem(null)
  }

  const handleDeleteChatSession = (e, idToDelete) => {
    e.stopPropagation()
    if (chatSessions.length <= 1) {
      handleNewChat()
      setChatSessions((prev) => prev.filter((s) => s.id !== idToDelete))
      return
    }
    const remaining = chatSessions.filter((s) => s.id !== idToDelete)
    setChatSessions(remaining)
    if (activeSessionId === idToDelete) setActiveSessionId(remaining[0].id)
  }

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
            is_artifact: true
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
          merged[fname] = { ...(merged[fname] || {}), content: txt }
        }
      })
    }
    return merged
  }

      const fetchTaasArtifacts = async (preferredFile = null, forceSync = false) => {
        try {
          const res = await axios.get(`${API_BASE}/api/taas/artifacts`, {
            params: forceSync ? { sync: true } : {}
          })
          const merged = normalizeBackendFiles(res.data.files, res.data.raw_files)
          setArtifactFiles(merged)
          const targetFile = preferredFile || selectedFile
          if (merged[targetFile] && (!editorDirty || forceSync)) {
            setEditorContent(merged[targetFile].content)
            if (forceSync) setEditorDirty(false)
          }
          if (res.data.pending_plan?.status === 'AWAITING_APPROVAL') {
            setPendingPlan(res.data.pending_plan)
          } else {
            setPendingPlan(null)
          }
        } catch (err) {
          console.warn('Using starter templates:', err.message)
        }
      }

        const fetchTaasResources = async (forceSync = false) => {
          setLoadingResources(true)
          try {
            const res = await axios.get(`${API_BASE}/api/taas/resources`, {
              params: forceSync ? { sync: true } : {}
            })
            setTaasResources(res.data)
          } catch (err) {
            console.warn('Could not load resources:', err.message)
          } finally {
            setLoadingResources(false)
          }
        }

        const handleSyncTerraformState = async (preferredFile = null) => {
          const targetFile = preferredFile || selectedFile
          setLoadingResources(true)
          setEditorStatusMsg('Syncing remote GCS Terraform state & HCL artifacts...')
          try {
            const res = await axios.post(`${API_BASE}/api/taas/sync`)
            const merged = normalizeBackendFiles(res.data.files, res.data.raw_files)
            setArtifactFiles(merged)
            if (merged[targetFile]) {
              setEditorContent(merged[targetFile].content)
              setEditorDirty(false)
            }
            if (res.data.resources) {
              setTaasResources(res.data.resources)
            } else {
              await fetchTaasResources(false)
            }
            if (res.data.pending_plan?.status === 'AWAITING_APPROVAL') {
              setPendingPlan(res.data.pending_plan)
            } else {
              setPendingPlan(null)
            }
            const activeCount =
              res.data.sync_result?.active_in_state ??
              res.data.resources?.active_count ??
              0
            setEditorStatusMsg(`✓ Synced with remote GCS state (${activeCount} active resources in state).`)
          } catch (err) {
            setEditorStatusMsg(`Sync failed: ${err.response?.data?.detail || err.message}`)
          } finally {
            setLoadingResources(false)
          }
        }

        const handleEditorKeyDown = (e) => {
          if ((e.ctrlKey || e.metaKey) && (e.key === '/' || e.code === 'Slash')) {
            e.preventDefault()
            const textarea = e.target
            const start = textarea.selectionStart
            const end = textarea.selectionEnd
            const value = editorContent || ''

            const lineStart = value.lastIndexOf('\n', start - 1) + 1
            const effectiveEnd = end > start && value[end - 1] === '\n' ? end - 1 : end
            const nextNewline = value.indexOf('\n', effectiveEnd)
            const lineEnd = nextNewline === -1 ? value.length : nextNewline

            const block = value.slice(lineStart, lineEnd)
            const lines = block.split('\n')
            const nonEmptyLines = lines.filter((l) => l.trim().length > 0)
            const allCommented =
              nonEmptyLines.length > 0 && nonEmptyLines.every((l) => /^\s*#/.test(l))

            const updatedLines = allCommented
              ? lines.map((l) => l.replace(/^(\s*)# ?/, '$1'))
              : lines.map((l) => (l.trim().length === 0 && lines.length > 1 ? l : `# ${l}`))

            const newBlock = updatedLines.join('\n')
            const newValue = value.slice(0, lineStart) + newBlock + value.slice(lineEnd)

            setEditorContent(newValue)
            setEditorDirty(true)

            requestAnimationFrame(() => {
              if (start === end) {
                const delta = newBlock.length - block.length
                const newCursor = Math.max(lineStart, start + delta)
                textarea.setSelectionRange(newCursor, newCursor)
              } else {
                textarea.setSelectionRange(lineStart, lineStart + newBlock.length)
              }
            })
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
            setEditorStatusMsg(`Loaded starter template for ${selectedFile}.`)
          }
        }

        const handleSaveArtifactCode = async () => {
          setSavingFile(true)
          setEditorStatusMsg('Saving & formatting...')
          try {
            const res = await axios.post(`${API_BASE}/api/taas/artifacts/update`, {
              file_name: selectedFile,
              code_content: editorContent
            })
            if (res.data.status === 'SUCCESS') {
              setEditorContent(res.data.content || res.data.updated_content || editorContent)
              setEditorDirty(false)
              setEditorStatusMsg(`✓ Saved to artifacts/gcp/${selectedFile}.`)
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
          if (editorDirty) await handleSaveArtifactCode()
          setRunningPlanOrApply(true)
          updateActiveSessionMessages((prev) => [
            ...prev,
            { role: 'user', content: `Run \`terraform plan\` on \`artifacts/gcp/${selectedFile}\`` }
          ])
          try {
            const res = await axios.post(`${API_BASE}/api/taas/plan`, { file_name: selectedFile })
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
              updateActiveSessionMessages((prev) => [
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
              updateActiveSessionMessages((prev) => [
                ...prev,
                {
                  role: 'assistant',
                  content: `### Plan Status: \`${data.status}\`\n\n${data.message || ''}\n\n\`\`\`\n${data.details || ''}\n\`\`\``
                }
              ])
            }
            await fetchTaasArtifacts(selectedFile)
          } catch (err) {
            updateActiveSessionMessages((prev) => [
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
          updateActiveSessionMessages((prev) => [
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
              updateActiveSessionMessages((prev) => [
                ...prev,
                {
                  role: 'assistant',
                  content:
                    `### Terraform Apply Succeeded (\`${data.plan_id}\`)\n\n${data.message}\n\n` +
                    `\`\`\`\n${(data.apply_output || '').slice(-1800)}\n\`\`\``
                }
              ])
              setPendingPlan(null)
            } else if (data.status === 'CANCELLED') {
              updateActiveSessionMessages((prev) => [
                ...prev,
                { role: 'assistant', content: `### Plan Cancelled (\`${data.plan_id}\`)\n\n${data.message}` }
              ])
              setPendingPlan(null)
            } else {
              updateActiveSessionMessages((prev) => [
                ...prev,
                { role: 'assistant', content: `### Apply Status: \`${data.status}\`\n\n${data.message || ''}` }
              ])
            }
            await fetchTaasArtifacts(selectedFile)
            await fetchTaasResources()
          } catch (err) {
            updateActiveSessionMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `Error confirming plan: ${err.response?.data?.detail || err.message}` }
            ])
          } finally {
            setRunningPlanOrApply(false)
          }
        }

        const handleChatSend = async (customPrompt = null) => {
          const promptText = (customPrompt ?? taasInput).trim()
          if (!promptText || taasLoading) return

          updateActiveSessionMessages((prev) => [...prev, { role: 'user', content: promptText }])
          if (!customPrompt) setTaasInput('')
          setTaasLoading(true)

          if (selectedService === 'dataops') {
            try {
              const res = await axios.post(`${API_BASE}/api/dataops/chat`, {
                message: promptText,
                session_id: activeSessionId
              })
              updateActiveSessionMessages((prev) => [
                ...prev,
                { role: 'assistant', content: res.data.response || 'Completed.' }
              ])
            } catch (err) {
              updateActiveSessionMessages((prev) => [
                ...prev,
                { role: 'assistant', content: `Error querying Agentic DataOps: ${err.message}` }
              ])
            } finally {
              setTaasLoading(false)
            }
            return
          }

          // If user is replying to a 1-Click TaaS chat question (name + region), combine into full agent request
          const outboundMessage =
            pendingOneClickItem && !customPrompt
              ? pendingOneClickItem.buildAgentPrompt(promptText)
              : promptText
          if (pendingOneClickItem) {
            setPendingOneClickItem(null)
          }

          try {
            const res = await axios.post(`${API_BASE}/api/taas/chat`, {
              message: outboundMessage,
              session_id: activeSessionId
            })
            updateActiveSessionMessages((prev) => [
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
            if (res.data.pending_plan?.status === 'AWAITING_APPROVAL') {
              setPendingPlan(res.data.pending_plan)
            } else {
              setPendingPlan(null)
            }
            fetchTaasResources()
          } catch (err) {
            updateActiveSessionMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `Error communicating with TaaS Agent: ${err.response?.data?.detail || err.message}` }
            ])
          } finally {
            setTaasLoading(false)
          }
        }

        const handleOpenResourcePrompt = (item) => {
          if (item.defaultFile && artifactFiles[item.defaultFile]) {
            handleSelectArtifactFile(item.defaultFile)
          }
          setPendingOneClickItem(item)
          updateActiveSessionMessages((prev) => [
            ...prev,
            { role: 'user', content: item.userTrigger },
            { role: 'assistant', content: item.assistantAsk }
          ])
        }

        const handleDeactivateResource = async (category, resourceName) => {
          setLoadingResources(true)
          try {
            const res = await axios.post(`${API_BASE}/api/taas/resources/deactivate`, {
              resource_category: category,
              resource_name: resourceName
            })
            updateActiveSessionMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `**Deactivation Plan Created for \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}` }
            ])
            await fetchTaasArtifacts(selectedFile)
            await fetchTaasResources()
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
            updateActiveSessionMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `**Recreation Plan Created for \`${category}.${resourceName}\`:** ${res.data.message || res.data.status}` }
            ])
            await fetchTaasArtifacts(selectedFile)
            await fetchTaasResources()
          } finally {
            setLoadingResources(false)
          }
        }

        const handleEnterpriseChat = async (customText = null) => {
          const text = (customText ?? basicChatInput).trim()
          if (!text || basicChatLoading) return
          if (!customText) setBasicChatInput('')
          setBasicChatLoading(true)
          setEntMessages((prev) => [...prev, { role: 'user', content: text }])
          try {
            const res = await axios.post(`${API_BASE}/api/enterprise/chat`, { query: text, role: authUser.role })
            setEntMessages((prev) => [...prev, { role: 'assistant', content: res.data.response || 'Done.' }])
          } catch (err) {
            setEntMessages((prev) => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
          } finally {
            setBasicChatLoading(false)
          }
        }

        // LOGIN SCREEN
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

        // ENTERPRISE GPT VIEW (HR / EMPLOYEE)
        if (authUser.role === 'hr' || authUser.role === 'employee') {
          const isEntEmpty = entMessages.length === 0 && !basicChatLoading
          return (
            <div className="platform-shell">
              <aside className="platform-sidebar">
                <button className="new-chat-btn" onClick={() => setEntMessages([])}>
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
                  {isEntEmpty ? (
                    <div className="gemini-center-stage">
                      <div className="gemini-hero-chips">
                        <span className="hero-chip"><Sparkles size={13} /> Role: <strong>{authUser.displayName}</strong></span>
                        <span className="hero-chip"><Database size={13} /> BigQuery + ChromaDB</span>
                      </div>
                      <h1 className="gemini-hero-title">
                        Hello, <span className="gemini-gradient-text">{authUser.displayName}</span>
                      </h1>
                      <p className="gemini-hero-subtitle">Ask about bench talent, resumes, or company HR policies.</p>
                      <div className="gemini-center-composer-wrap">
                        <div className="floating-composer gemini-elevated-composer">
                          <Sparkles size={18} className="composer-lead-icon" />
                          <input
                            type="text"
                            placeholder="Message EnterpriseGPT..."
                            value={basicChatInput}
                            onChange={(e) => setBasicChatInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleEnterpriseChat()}
                          />
                          <button className="composer-send-btn" onClick={() => handleEnterpriseChat()}>
                            <Send size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
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
                            <div className="bubble-card typing-indicator"><ThinkingSpheres /></div>
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
                          <button className="composer-send-btn" onClick={() => handleEnterpriseChat()}>
                            <Send size={16} />
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>

              </main>
            </div>
          )
        }

        // DEVELOPER VIEW (TAAS STUDIO & AGENTIC DATAOPS)
        const currentFileMeta = artifactFiles[selectedFile] || DEFAULT_STARTER_FILES[selectedFile] || {}
        const archivedTotalCount = Object.values(taasResources.deactivated || {}).reduce(
          (acc, list) => acc + (list?.length || 0),
          0
        )
        const isChatEmpty = taasMessages.length === 0 && !taasLoading && !runningPlanOrApply && !pendingPlan

        return (
          <div className="platform-shell">

            {/* LEFT SIDEBAR */}
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
                  <div className="umbrella-catalog-list">
                    {TAAS_UMBRELLA_CATALOG.map((group) => {
                      const GroupIcon = group.icon
                      const isOpen = openUmbrella === group.id
                      return (
                        <div key={group.id} className={`umbrella-group ${isOpen ? 'open' : ''}`}>
                          <button
                            type="button"
                            className="umbrella-header-btn"
                            onClick={() => setOpenUmbrella((prev) => (prev === group.id ? '' : group.id))}
                          >
                            <span className="umbrella-title-left">
                              <GroupIcon size={14} className="umbrella-icon" />
                              <span>{group.label}</span>
                            </span>
                            <ChevronRight size={14} className={`umbrella-chevron ${isOpen ? 'rotated' : ''}`} />
                          </button>
                          {isOpen && (
                            <div className="umbrella-children">
                              {group.items.map((item) => (
                                <button
                                  key={item.id}
                                  type="button"
                                  className="umbrella-item-btn"
                                  onClick={() => handleOpenResourcePrompt(item)}
                                >
                                  <span className="umbrella-item-dot" />
                                  <span>{item.label}</span>
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )
                    })}

                    <button
                      type="button"
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

            {/* MAIN WORKSPACE */}
            <main className="platform-main">
              <header className="minimal-topbar">
                <div className="custom-dropdown-container" ref={dropdownRef}>
                  <button
                    type="button"
                    className={`custom-dropdown-trigger ${dropdownOpen ? 'open' : ''}`}
                    onClick={() => setDropdownOpen((prev) => !prev)}
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
                          <span>Pre-Plan Code, Active Resources & GCP Provisioning</span>
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

                <div className="topbar-right-controls" />
              </header>

              {selectedService === 'taas' ? (
                <div
                  ref={workspaceContainerRef}
                  className={`taas-workspace-container ${panelCollapsed ? 'panel-collapsed' : ''} ${isDraggingPanel ? 'is-resizing' : ''}`}
                >
                  {/* LEFT PANE: Chat starts in the middle like Gemini when empty */}
                  <section className="taas-chat-column">
                    {isChatEmpty ? (
                      <div className="gemini-center-stage">
                        <div className="gemini-hero-chips">
                          <span className="hero-chip"><Sparkles size={13} /> Project: <strong>solar-dialect-264808</strong></span>
                          <span className="hero-chip"><Cloud size={13} /> Region: <strong>asia-south2</strong></span>
                        </div>

                        <h1 className="gemini-hero-title">
                          What infrastructure <span className="gemini-gradient-text">shall we build?</span>
                        </h1>
                        <p className="gemini-hero-subtitle">
                          Ask in chat or customize HCL in the sidecar panel, then click <strong>Plan</strong>.
                        </p>

                        <div className="gemini-center-composer-wrap">
                          <div className="floating-composer gemini-elevated-composer">
                            <Sparkles size={18} className="composer-lead-icon" />
                            <input
                              type="text"
                              placeholder="Ask TaaS to create or customize GCP infrastructure..."
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

                        <div className="gemini-quick-cards">
                          <button
                            type="button"
                            className="gemini-quick-card"
                            onClick={() => handleOpenResourcePrompt(TAAS_UMBRELLA_CATALOG[0].items[0])}
                          >
                            <div className="qcard-icon indigo"><Database size={16} /></div>
                            <div className="qcard-body">
                              <strong>BigQuery Dataset</strong>
                              <span>Analytics dataset</span>
                            </div>
                          </button>
                          <button
                            type="button"
                            className="gemini-quick-card"
                            onClick={() => handleOpenResourcePrompt(TAAS_UMBRELLA_CATALOG[0].items[1])}
                          >
                            <div className="qcard-icon blue"><Database size={16} /></div>
                            <div className="qcard-body">
                              <strong>BigQuery Table</strong>
                              <span>Table in dataset</span>
                            </div>
                          </button>
                          <button
                            type="button"
                            className="gemini-quick-card"
                            onClick={() => handleOpenResourcePrompt(TAAS_UMBRELLA_CATALOG[1].items[0])}
                          >
                            <div className="qcard-icon cyan"><HardDrive size={16} /></div>
                            <div className="qcard-body">
                              <strong>Storage Bucket</strong>
                              <span>GCS storage bucket</span>
                            </div>
                          </button>
                          <button
                            type="button"
                            className="gemini-quick-card"
                            onClick={() => handleOpenResourcePrompt(TAAS_UMBRELLA_CATALOG[2].items[0])}
                          >
                            <div className="qcard-icon violet"><Server size={16} /></div>
                            <div className="qcard-body">
                              <strong>Pub/Sub Topic</strong>
                              <span>Event streaming topic</span>
                            </div>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
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
                              <div className="bubble-card typing-indicator"><ThinkingSpheres /></div>
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
                                {runningPlanOrApply ? <Loader2 className="spin" size={15} /> : approvalDecision === 'apply' ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                                <span>Confirm</span>
                              </button>
                            </div>
                          </div>
                        )}

                        <div className="floating-composer-wrap">
                          <div className="floating-composer">
                            <input
                              type="text"
                              placeholder="Ask TaaS to create or customize GCP infrastructure..."
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
                      </>
                    )}
                  </section>

                  {/* CURSOR DRAG SPLITTER */}
                  {!panelCollapsed && (
                    <div
                      className={`antigravity-resize-splitter ${isDraggingPanel ? 'dragging' : ''}`}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        setIsDraggingPanel(true)
                      }}
                      onDoubleClick={() => setPanelWidthPct(54)}
                      title="Drag to resize panel"
                    >
                      <div className="splitter-grip-bar" />
                    </div>
                  )}

                  {/* RIGHT PANE: Pre-Plan Code, Active Resources + State Badge */}
                  <section
                    className={`antigravity-side-panel ${panelCollapsed ? 'size-collapsed' : 'size-custom'} ${isDraggingPanel ? 'is-dragging' : ''}`}
                    style={!panelCollapsed ? { width: `${panelWidthPct}%` } : undefined}
                  >
                    {panelCollapsed ? (
                      <div className="collapsed-sidecar-rail">
                        <button className="rail-icon-btn" onClick={() => setPanelCollapsed(false)} title="Expand Panel">
                          <PanelRightOpen size={17} />
                        </button>
                        <button
                          className={`rail-icon-btn ${taasRightTab === 'editor' ? 'active' : ''}`}
                          onClick={() => { setTaasRightTab('editor'); setPanelCollapsed(false) }}
                          title="Pre-Plan Code"
                        >
                          <Code2 size={17} />
                        </button>
                        <button
                          className={`rail-icon-btn ${taasRightTab === 'resources' ? 'active' : ''}`}
                          onClick={() => { setTaasRightTab('resources'); setPanelCollapsed(false); fetchTaasResources() }}
                          title="Active Resources"
                        >
                          <Layers size={17} />
                        </button>
                      </div>
                    ) : (
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

                          {/* State File Path Badge + Minimize Button on the Right Panel */}
                          <div className="panel-window-controls">
                            <div className="workbench-state-pill" title="Authoritative GCS Remote State">
                              <span className="state-dot" />
                              <span>State: <code>taas/solar-dialect-264808/gcp</code></span>
                            </div>
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

                        {taasRightTab === 'editor' && (
                          <div className="editor-pane">
                            <div className="file-tabs-bar">
                              {ARTIFACT_FILE_LIST.map((f) => {
                                const meta = artifactFiles[f.name] || DEFAULT_STARTER_FILES[f.name]
                                return (
                                  <button
                                    key={f.name}
                                    className={`file-tab-pill ${selectedFile === f.name ? 'selected' : ''}`}
                                    onClick={() => handleSelectArtifactFile(f.name)}
                                  >
                                    <FileCode size={13} />
                                    <span>{f.label}</span>
                                    {meta?.is_artifact && <span className="resource-dot" />}
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
                                <button className="tool-btn secondary" onClick={handleLoadStarterTemplate}>
                                  <RotateCcw size={13} /> Starter
                                </button>
                                  <button className="tool-btn secondary" onClick={() => handleSyncTerraformState(selectedFile)} disabled={loadingResources} title="Sync local HCL files with remote GCS Terraform state">
                                    <RefreshCw className={loadingResources ? 'spin' : ''} size={13} /> Sync
                                  </button>
                                  <button className="tool-btn primary" onClick={handleSaveArtifactCode} disabled={savingFile}>
                                    {savingFile ? <Loader2 className="spin" size={13} /> : <Save size={13} />}
                                    <span>Save to Artifacts</span>
                                  </button>
                                  <button className="tool-btn plan-btn" onClick={handleRunTerraformPlan} disabled={runningPlanOrApply}>
                                    {runningPlanOrApply ? <Loader2 className="spin" size={13} /> : <Play size={13} />}
                                    <span>Plan</span>
                                  </button>
                              </div>
                            </div>

                            {editorStatusMsg && <div className="editor-status-banner">{editorStatusMsg}</div>}

                            <textarea
                              className="hcl-code-textarea"
                              value={editorContent}
                              onKeyDown={handleEditorKeyDown}
                              onChange={(e) => {
                                setEditorContent(e.target.value)
                                setEditorDirty(true)
                              }}
                              spellCheck={false}
                            />
                          </div>
                        )}

                        {taasRightTab === 'resources' && (
                          <div className="resources-pane">
                            <div className="resources-hero-banner">
                              <div className="hero-left">
                                <div className="hero-icon-circle"><ShieldCheck size={20} /></div>
                                <div>
                                  <h4>Cloud Infrastructure Inventory</h4>
                                  <p>Authoritative GCS State: <code>taas/solar-dialect-264808/gcp</code></p>
                                </div>
                              </div>
                                <button className="tool-btn secondary" onClick={() => handleSyncTerraformState(selectedFile)} disabled={loadingResources}>
                                  <RefreshCw className={loadingResources ? 'spin' : ''} size={13} /> Sync State
                                </button>
                            </div>

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

                            <div className="resources-filter-bar">
                              <div className="filter-pills-group">
                                <button type="button" className={`filter-pill-btn ${resourceFilter === 'all' ? 'active' : ''}`} onClick={() => setResourceFilter('all')}>All</button>
                                <button type="button" className={`filter-pill-btn ${resourceFilter === 'active' ? 'active' : ''}`} onClick={() => setResourceFilter('active')}>Active ({taasResources.active_count || 0})</button>
                                <button type="button" className={`filter-pill-btn ${resourceFilter === 'archived' ? 'active' : ''}`} onClick={() => setResourceFilter('archived')}>Deactivated ({archivedTotalCount})</button>
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

                            <div className="resource-groups-scroll">
                              {resourceFilter !== 'archived' &&
                                Object.entries(taasResources.active || {}).map(([category, items]) => {
                                  const meta = CATEGORY_METADATA[category] || { label: category.toUpperCase(), file: `${category}.tf`, icon: Cloud }
                                  const IconComp = meta.icon
                                  const filteredItems = (items || []).filter((item) =>
                                    !resourceSearch.trim() || item.cloud_name?.toLowerCase().includes(resourceSearch.toLowerCase())
                                  )
                                  return (
                                    <div key={category} className="resource-category-card">
                                      <div className="cat-header">
                                        <div className="cat-title-wrap">
                                          <span className="cat-service-badge"><IconComp size={15} /></span>
                                          <strong>{meta.label}</strong>
                                        </div>
                                        <span className={`count-badge ${filteredItems.length === 0 ? 'zero' : ''}`}>{filteredItems.length} active</span>
                                      </div>
                                      {filteredItems.length === 0 ? (
                                        <p className="empty-text">No active resources deployed in <code>{meta.file}</code></p>
                                      ) : (
                                        <div className="resource-list">
                                          {filteredItems.map((item, i) => (
                                            <div key={i} className="resource-row-item">
                                              <div className="res-item-left">
                                                <div className="res-top-line">
                                                  <span className="live-status-dot" />
                                                  <span className="res-cloud-title">{item.cloud_name}</span>
                                                  <code className="res-tf-chip">{meta.file}</code>
                                                </div>
                                                <span className="res-meta-line">Project: <strong>{item.project_id || 'solar-dialect-264808'}</strong></span>
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
                                  const filteredArchived = (items || []).filter((item) =>
                                    !resourceSearch.trim() || item.cloud_name?.toLowerCase().includes(resourceSearch.toLowerCase())
                                  )
                                  if (filteredArchived.length === 0) return null
                                  const meta = CATEGORY_METADATA[category] || { label: category.toUpperCase(), file: `${category}.tf`, icon: Layers }
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
                  {isChatEmpty ? (
                    <div className="gemini-center-stage">
                      <div className="gemini-hero-chips">
                        <span className="hero-chip"><Activity size={13} /> Dataset: <strong>servicenow_itsm.incidents</strong></span>
                        <span className="hero-chip"><Database size={13} /> Project: <strong>solar-dialect-264808</strong></span>
                      </div>
                      <h1 className="gemini-hero-title">
                        What operational insights <span className="gemini-gradient-text">do you need?</span>
                      </h1>
                      <p className="gemini-hero-subtitle">Analyze ServiceNow incidents, MTTR trends, and P1/P2 backlog on BigQuery.</p>
                      <div className="gemini-center-composer-wrap">
                        <div className="floating-composer gemini-elevated-composer">
                          <Activity size={18} className="composer-lead-icon" />
                          <input
                            type="text"
                            placeholder="Ask Agentic DataOps about ServiceNow incidents, MTTR, or backlog aging..."
                            value={taasInput}
                            onChange={(e) => setTaasInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleChatSend()}
                          />
                          <button className="composer-send-btn" onClick={() => handleChatSend()} disabled={!taasInput.trim()}>
                            <Send size={16} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
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
                            <div className="bubble-card typing-indicator"><ThinkingSpheres /></div>
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
                    </>
                  )}
                </div>
              )}
            </main>
          </div>
        )
      }

