from pydantic import BaseModel, Field
from core.permissions import PermissionLevel
from tools.registry import ToolDefinition, registry
from services.rag import RagService
from core.retriever import LexicalRetriever
from core.db import SessionLocal
import json

class IngestDocumentSchema(BaseModel):
    file_path: str = Field(..., description="Absolute path to the document file (PDF, DOCX, TXT, MD, CSV)")
    mime_type: str = Field(None, description="Optional mime type")

class SearchDocumentsSchema(BaseModel):
    query: str = Field(..., description="Search query for filename")
    limit: int = Field(5, description="Max results")

class GetDocumentSchema(BaseModel):
    document_id: str = Field(..., description="ID of the document")

def execute_ingest_document(file_path: str, mime_type: str = None, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = RagService(db, LexicalRetriever())
        try:
            doc_id = svc.ingest_document(user_id, file_path, mime_type)
            return f"Document ingested successfully. ID: {doc_id}"
        except Exception as e:
            return f"Error ingesting document: {e}"

def execute_search_documents(query: str, limit: int = 5, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = RagService(db, LexicalRetriever())
        docs = svc.search_documents(user_id, query, limit)
        if not docs: return "No documents found."
        return json.dumps([{"id": d.id, "filename": d.filename, "size": d.size} for d in docs])

def execute_get_document(document_id: str, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = RagService(db, LexicalRetriever())
        doc = svc.get_document(user_id, document_id)
        if not doc: return "Document not found."
        return json.dumps({"id": doc.id, "filename": doc.filename, "size": doc.size, "chunks": len(doc.chunks)})

registry.register(ToolDefinition(
    name="ingest_document",
    description="Ingest a document (PDF, DOCX, TXT, MD, CSV) into the RAG knowledge base. Ensure file is within sandbox.",
    schema=IngestDocumentSchema,
    executor=execute_ingest_document,
    permission_level=PermissionLevel.MODIFY
))

registry.register(ToolDefinition(
    name="search_documents",
    description="Search for ingested documents by filename.",
    schema=SearchDocumentsSchema,
    executor=execute_search_documents,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="get_document",
    description="Get metadata for a specific document by ID.",
    schema=GetDocumentSchema,
    executor=execute_get_document,
    permission_level=PermissionLevel.READ
))
