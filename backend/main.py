import os
import shutil
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import List, Optional

# Load environment variables from the root directory
load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))


from modules.extractor import CompleteXERExtractor
from modules.analyzer import XERAnalyzer

app = FastAPI()

# Enable CORS for React/Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer = XERAnalyzer()

@app.get("/")
def read_root():
    return {"status": "ok"}

@app.post("/upload-xer")
async def upload_xer(file: UploadFile = File(...), file_type: str = Form("baseline"), context: str = Form("audit")):
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, file.filename)
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        print(f"--- Processing {file_type} upload: {file.filename} ---")
        extractor = CompleteXERExtractor(temp_path, file_type)
        extractor.extract_all()
        data = extractor.get_complete_data()
        
        version_id = analyzer.data_store.add_version(
            data, 
            data['project']['project_name'], 
            data['project']['data_date'],
            type=file_type,
            context=context
        )
        print(f"Version added: {version_id} ({data['project']['project_name']})")
            
        stats = analyzer.get_basic_stats(context=context)
        os.remove(temp_path)
        return {"success": True, "stats": stats, "version_id": version_id}
    except Exception as e:
        print(f"ERROR during upload: {str(e)}")
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def get_health(version_id: Optional[str] = None, context: str = "audit"):
    return analyzer.get_basic_stats(version_id, context=context)

@app.get("/critical-path")
async def get_critical_path(context: str = "audit"):
    # Example logic: filter tasks with float <= 0
    latest = analyzer.data_store.get_latest(context=context)
    if not latest: return []
    tasks = latest['df']['tasks'].copy()
    tasks['float'] = pd.to_numeric(tasks['total_float_hr_cnt'], errors='coerce').fillna(0)
    critical = tasks[tasks['float'] <= 0]
    return critical.head(100).to_dict('records')

@app.post("/ask")
async def ask_question(query: str = Form(...), context: Optional[str] = Form(None), session_id: str = Form("default")):
    ctx_dict = None
    if context:
        try:
            import json
            ctx_dict = json.loads(context)
        except:
            pass
            
    # Use the new modular analytical engine
    response = analyzer.analyze(query, context=ctx_dict, session_id=session_id)
    return {"response": response}

@app.get("/settings")
async def get_settings():
    return analyzer.get_config()

@app.post("/settings/update")
async def update_settings(provider: str = Form(...), model: Optional[str] = Form(None)):
    return analyzer.set_config(provider, model)

@app.get("/versions")
async def get_versions(context: str = "audit"):
    """Returns list of all uploaded schedule versions for a context"""
    versions = []
    ctx = analyzer.data_store.contexts.get(context, analyzer.data_store.contexts["audit"])
    for v in ctx["versions"].values():
        versions.append({
            "id": v["id"],
            "type": v["type"],
            "name": v["name"],
            "data_date": v["data_date"]
        })
    # Sort updates by date, baseline first
    versions.sort(key=lambda x: (0 if x["type"] == "baseline" else 1, x["data_date"]))
    return versions

@app.delete("/versions/{version_id}")
async def delete_version(version_id: str, context: str = "audit"):
    """Deletes a specific schedule version"""
    try:
        analyzer.data_store.remove_version(version_id, context=context)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/xer-data")
async def get_xer_data(table: str = "TASK", search: str = "", page: int = 1, limit: int = 100, version_id: Optional[str] = None, filter: str = "ALL", context: str = "audit"):
    offset = (page - 1) * limit
    try:
        data = analyzer.data_store.get_table_data(table, search, limit, offset, source_id=version_id, filter_type=filter, context=context)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)
