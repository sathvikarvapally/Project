# app/schemas.py
from pydantic import BaseModel
from typing import Optional, List, Dict

class DocumentCreate(BaseModel):
    filename: str
    content: str

class DocumentOut(BaseModel):
    id: int
    filename: str
    content: str
    doc_type: Optional[str]
    doc_confidence: Optional[str]

    class Config:
        orm_mode = True

class AnalysisOut(BaseModel):
    id: int
    document_id: int
    missing_fields: Optional[Dict]
    recommendations: Optional[str]

    class Config:
        orm_mode = True
