import os
import shutil
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
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

@app.post("/upload-xer")
async def upload_xer(file: UploadFile = File(...), file_type: str = Form("baseline")):
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
        
        if file_type == "baseline":
            analyzer.data_store.load_baseline(data, data['project']['project_name'], data['project']['data_date'])
            print(f"Baseline loaded: {data['project']['project_name']}")
        else:
            analyzer.data_store.add_update(data, data['project']['project_name'], data['project']['data_date'])
            print(f"Update added: {data['project']['project_name']}")
            
        stats = analyzer.get_basic_stats()
        print(f"Stats computed: {list(stats.keys())}")
        
        os.remove(temp_path)
        return {"success": True, "stats": stats}
    except Exception as e:
        print(f"ERROR during upload: {str(e)}")
        if os.path.exists(temp_path): os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def get_health():
    return analyzer.get_basic_stats()

@app.get("/critical-path")
async def get_critical_path():
    # Example logic: filter tasks with float <= 0
    latest = analyzer.data_store.get_latest()
    if not latest: return []
    tasks = latest['df']['tasks'].copy()
    tasks['float'] = pd.to_numeric(tasks['total_float_hr_cnt'], errors='coerce').fillna(0)
    critical = tasks[tasks['float'] <= 0]
    return critical.head(100).to_dict('records')

@app.post("/ask")
async def ask_question(query: str = Form(...)):
    response = analyzer.get_ai_response(query)
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
