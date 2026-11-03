"""EnterpriseGPT Service Layer.

Integrates:
- Resume & Policy Document Classification (Regex + NLP heuristics)
- Google Cloud Storage (GCS) document storage
- ChromaDB Vector Search (Resume & Policy RAG)
- Google BigQuery Structured Bench Employee Analytics (`employee_data`)
"""

import json
import os
import re
import shutil
from collections import Counter
from typing import List
from dotenv import load_dotenv
from fastapi import UploadFile
from google.cloud import bigquery, storage

load_dotenv()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploaded_docs")
os.makedirs(UPLOAD_DIR, exist_ok=True)

GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "enterprisegpt_bucket")
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "localhost")
CHROMA_SERVER_PORT = int(os.getenv("CHROMA_SERVER_PORT", "8001"))
PROJECT_ID = os.getenv("PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "solar-dialect-264808"))
DATASET = os.getenv("DATASET", "enterprisegpt")
TABLE = os.getenv("TABLE", "employee_data")
FULL_TABLE_NAME = f"`{PROJECT_ID}.{DATASET}.{TABLE}`"

_nlp = None
_vectorstore = None
_history_store: dict[str, list[dict]] = {}


def _get_nlp():
    """Lazy-load spaCy model if installed; otherwise use lightweight regex fallback."""
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    except Exception:
        _nlp = False
    return _nlp


def get_vectorstore():
    """Lazy-initialize and return the Chroma vector store."""
    global _vectorstore
    if _vectorstore is not None:
        return _vectorstore

    import chromadb
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings()
    client = chromadb.HttpClient(host=CHROMA_SERVER_HOST, port=CHROMA_SERVER_PORT)
    _vectorstore = Chroma(
        client=client,
        embedding_function=embeddings,
        collection_name="langchain",
    )
    return _vectorstore


def _generate_with_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
    """Run LLM generation using OpenAI if OPENAI_API_KEY is configured, else fallback to Gemini."""
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOpenAI(model="gpt-4.1", temperature=0)
        resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        return resp.content.strip()

    # Fallback to Google GenAI / Vertex AI Gemini
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.0,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    preferred_model = os.getenv("TAAS_MODEL", "gemini-3.5-flash-lite")
    candidates = [
        ("global", preferred_model),
        ("global", "gemini-2.5-flash"),
        ("us-central1", "gemini-2.5-flash"),
        ("global", "gemini-2.0-flash"),
    ]
    last_err = None
    for loc, mdl in candidates:
        try:
            client = genai.Client(api_key=api_key) if api_key else genai.Client(vertexai=True, project=PROJECT_ID, location=loc)
            resp = client.models.generate_content(model=mdl, contents=user_prompt, config=config)
            return (resp.text or "").strip()
        except Exception as err:
            last_err = err
            continue
    raise last_err or RuntimeError("Gemini generation failed.")


def extract_features(text: str) -> dict:
    """Extract heuristic features from text to classify it as 'resume' or 'policy'."""
    text_l = text.lower()
    features = {
        "has_email": bool(re.search(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", text)),
        "has_phone": bool(re.search(r"\b\d{10}\b|\+\d{1,3}[\s-]?\d{7,10}", text)),
        "years": len(re.findall(r"\b(19|20)\d{2}\b", text)),
        "bullets": text.count("•") + text.count("- "),
        "resume_sections": sum(
            s in text_l for s in ["experience", "education", "skills", "projects", "certification"]
        ),
        "policy_sections": sum(
            s in text_l
            for s in [
                "policy",
                "scope",
                "objective",
                "purpose",
                "guidelines",
                "compliance",
                "procedure",
                "applicability",
                "responsibility",
                "governance",
                "effective date",
                "revision",
                "approval",
                "authority",
                "definitions",
            ]
        ),
        "modal_verbs": sum(v in text_l for v in ["must", "shall", "required", "may not", "prohibited"]),
        "governance_terms": sum(
            t in text_l for t in ["act", "law", "regulation", "iso", "government", "ministry"]
        ),
        "person_entities": 0,
        "org_entities": 0,
    }

    nlp = _get_nlp()
    if nlp:
        doc = nlp(text[:15000])
        ent_counts = Counter(ent.label_ for ent in doc.ents)
        features["person_entities"] = ent_counts.get("PERSON", 0)
        features["org_entities"] = ent_counts.get("ORG", 0)

    return features


def classify_document(text: str) -> str:
    """Classify a document as 'resume' or 'policy' based on feature scores."""
    f = extract_features(text)
    resume_score = (
        f["has_email"] * 2
        + f["has_phone"] * 2
        + f["years"]
        + f["resume_sections"] * 2
        + f["bullets"]
        + f["person_entities"]
    )
    policy_score = (
        f["policy_sections"] * 2
        + f["modal_verbs"] * 2
        + f["org_entities"]
        + f["governance_terms"] * 3
        + (3 if f["bullets"] == 0 else 0)
    )
    return "resume" if resume_score >= policy_score else "policy"


def extract_employee_name_from_filename(filename: str) -> str | None:
    """Extract and format an employee's name from filename (first_last_date.ext)."""
    base_name = os.path.splitext(filename)[0]
    parts = base_name.split("_")
    if len(parts) < 2:
        return None
    first_name = parts[0].strip()
    last_name = parts[1].strip()
    if not first_name or not last_name:
        return None
    return f"{first_name.title()} {last_name.title()}"


def upload_to_gcs(source_file_path: str, destination_blob_name: str) -> str | None:
    """Upload a file to Google Cloud Storage (GCS)."""
    if not GCS_BUCKET_NAME:
        return None
    try:
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_path)
        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"
    except Exception as exc:
        print(f"[EnterpriseGPT] Failed to upload to GCS: {exc}")
        return None


def load_and_process_document(file_path: str):
    """Load a PDF, DOCX, or TXT document and split it into chunks."""
    from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
    elif ext == ".txt":
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        return []

    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=400)
    return splitter.split_documents(docs)


def is_bench_question(question: str) -> bool:
    """Check if a question asks about bench/unallocated employees."""
    keywords = [
        "bench",
        "on bench",
        "available employees",
        "free employees",
        "unallocated",
        "not assigned to project",
    ]
    q = question.lower()
    return any(k in q for k in keywords)


def query_bench_employees(question: str) -> list[dict]:
    """Generate and execute a BigQuery SQL query for bench employees."""
    sys_prompt = (
        f"You are an HR analytics assistant.\n"
        f"Write a BigQuery SELECT query ONLY using table {FULL_TABLE_NAME}.\n"
        f"Columns: id, name, department, is_on_bench (BOOL), bench_start_date (DATE), project_id, allocation_pct, last_updated_at.\n"
        f"Do NOT use markdown or backticks around the SQL. Return ONLY the SELECT statement."
    )
    sql = _generate_with_llm(sys_prompt, question)
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", sql.strip(), flags=re.IGNORECASE)
    client = bigquery.Client(project=PROJECT_ID)
    job = client.query(sql)
    return [dict(row) for row in job.result()]


def fetch_resume_links_for_bench(bench_names: set[str]) -> dict[str, str]:
    """Retrieve resume GCS links from ChromaDB for a set of employee names."""
    resume_links: dict[str, str] = {}
    try:
        vs = get_vectorstore()
        for name in bench_names:
            results = vs.get(
                where={"$and": [{"doc_type": "resume"}, {"employee_name": name}]},
                include=["metadatas"],
            )
            for meta in results.get("metadatas", []):
                if meta and meta.get("gcs_link"):
                    resume_links[name] = meta["gcs_link"]
                    break
    except Exception as exc:
        print(f"[EnterpriseGPT] VectorDB lookup warning: {exc}")
    return resume_links


async def process_uploaded_documents(files: List[UploadFile]) -> dict:
    """Process uploaded Resume & Policy documents (PDF, DOCX, TXT)."""
    processed_count = 0
    all_chunks = []
    for file in files:
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        docs = load_and_process_document(file_path)
        if not docs:
            continue

        sample_text = " ".join(d.page_content for d in docs[:3])
        doc_type = classify_document(sample_text)
        employee_name = extract_employee_name_from_filename(file.filename)
        gcs_link = upload_to_gcs(file_path, f"{doc_type}/{file.filename}")

        for d in docs:
            d.metadata.update(
                {
                    "doc_type": doc_type,
                    "employee_name": employee_name,
                    "source_file": file.filename,
                    "gcs_link": gcs_link,
                }
            )
        all_chunks.extend(docs)
        processed_count += 1

    if all_chunks:
        vs = get_vectorstore()
        vs.add_documents(all_chunks)

    return {
        "status": "success",
        "message": f"Successfully processed {processed_count} document(s).",
    }


RESUME_SYSTEM_PROMPT = """You are an expert HR Assistant.
Use the provided context to answer questions about candidates.
If the information is not found in the context, explicitly state that you don't know based on the documents.
Return ONLY valid JSON in the following format:
{
  "employee_name": "Full name of the employee",
  "summary": "2-3 line professional summary based strictly on the resume",
  "skills": ["skill1", "skill2"],
  "total_experience": "X years",
  "companies_worked_in": ["Company A", "Company B"],
  "resume_link": "The source link provided in the context"
}"""

POLICY_SYSTEM_PROMPT = """You are an HR Policy Assistant.
Answer the user's question strictly using the provided context.
- If the context lists types (e.g., Public Holidays, Restricted Holidays), enumerate them.
- If numeric counts are explicitly mentioned, extract and report them clearly.
- If the context provides a source link, include it in the response.
- Do NOT infer, assume, or hallucinate numbers."""


async def handle_enterprise_chat(message: str, portal: str = "employee") -> dict:
    """Handle EnterpriseGPT chat queries (Bench SQL, Resume RAG, and Policy RAG)."""
    # 1. Check Bench Employee query
    if is_bench_question(message):
        rows = query_bench_employees(message)
        names = {r["name"] for r in rows if "name" in r}
        resume_links = fetch_resume_links_for_bench(names)

        table = "| Name | Department | On Bench Since | Resume Link |\n|------|------------|----------------|-------------|\n"
        for r in rows:
            name = r.get("name", "Unknown")
            dept = r.get("department", "—")
            since = r.get("bench_start_date", "—")
            link = resume_links.get(name, "Not available")
            link_md = f"[Download]({link})" if link != "Not available" else "Not available"
            table += f"| {name} | {dept} | {since} | {link_md} |\n"
        return {"response": table}

    # 2. VectorDB Retrieval for Resumes or Policies
    vs = get_vectorstore()
    results = vs.get(include=["metadatas"])
    employee_names = {
        m["employee_name"]
        for m in results.get("metadatas", [])
        if m and m.get("employee_name")
    }
    is_resume = any(name.lower() in message.lower() for name in employee_names)
    filter_dict = {"doc_type": "resume"} if is_resume else {"doc_type": "policy"}

    retriever = vs.as_retriever(search_kwargs={"k": 15, "filter": filter_dict})
    docs = retriever.invoke(message)

    formatted_chunks = []
    for doc in docs:
        content = doc.page_content
        link = doc.metadata.get("gcs_link", "N/A")
        formatted_chunks.append(f"Content: {content}\nSource Link: {link}")
    context_str = "\n\n".join(formatted_chunks)

    if is_resume:
        raw_json = _generate_with_llm(
            RESUME_SYSTEM_PROMPT,
            f"Context:\n{context_str}\n\nQuestion: {message}",
            json_mode=True,
        )
        raw_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_json.strip(), flags=re.IGNORECASE)
        answer = json.loads(raw_json)
        response = (
            f"- **Name**:\n  - {answer.get('employee_name', 'Not found in documents')}\n"
            f"- **Summary**:\n  - {answer.get('summary', 'Not found in documents')}\n"
            "- **Skills**:\n"
            + "\n".join(f"  - {s}" for s in answer.get("skills", []))
            + f"\n- **Total Experience**:\n  - {answer.get('total_experience', 'Not found in documents')}\n"
            "- **Companies Worked In**:\n"
            + "\n".join(f"  - {c}" for c in answer.get("companies_worked_in", []))
            + f"\n- **Download Resume**:\n  - [Click here to download]({answer.get('resume_link', '#')})\n"
        )
    else:
        response = _generate_with_llm(
            POLICY_SYSTEM_PROMPT,
            f"Context:\n{context_str}\n\nQuestion: {message}",
            json_mode=False,
        )

    return {"response": response}

