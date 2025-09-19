## app/main.py
import os
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import aiofiles
import shutil
from PyPDF2 import PdfReader

# 🔹 Absolute imports (fixed)
from . import models, schemas
from .database import engine, SessionLocal
from .llm_adapter import classify_document, find_missing_fields

# create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="LLM Document Analyzer")

# mount static files
project_root = os.path.dirname(os.path.dirname(__file__))
static_dir = os.path.join(project_root, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

UPLOAD_DIR = os.path.join(project_root, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = os.path.join(static_dir, "index.html")
    return FileResponse(html_path)

@app.post("/upload", response_model=schemas.DocumentOut)
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDFs are supported.")
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    async with aiofiles.open(save_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    # extract text
    try:
        reader = PdfReader(save_path)
        text = []
        for p in reader.pages:
            page_text = p.extract_text()
            if page_text:
                text.append(page_text)
        full_text = "\n\n".join(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read PDF: {e}")

    # classify
    doc_type, confidence = classify_document(full_text)

    # store in DB
    doc = models.Document(
        filename=file.filename,
        content=full_text,
        doc_type=doc_type,
        doc_confidence=str(confidence)
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return doc

@app.get("/documents/{doc_id}", response_model=schemas.DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@app.post("/analyze/{doc_id}", response_model=schemas.AnalysisOut)
def analyze_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    analysis_res = find_missing_fields(doc.content, doc.doc_type)
    analysis = models.Analysis(
        document_id=doc.id,
        missing_fields=analysis_res,
        recommendations=analysis_res.get("recommendations")
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis

@app.get("/documents", response_model=list[schemas.DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(models.Document).order_by(models.Document.created_at.desc()).all()
    return docs
