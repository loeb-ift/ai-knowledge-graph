"""
知識圖譜生成服務 v2.0

[安裝部署]
1. 創建虛擬環境並安裝依賴：
   python -m venv venv
   source venv/bin/activate
   pip install fastapi==0.68.0 uvicorn==0.15.0 python-multipart==0.0.5 sqlalchemy==1.4.35 psycopg2-binary==2.9.5

2. 數據庫準備 (PostgreSQL)：
   在開始使用知識圖譜生成服務之前，您需要準備 PostgreSQL 數據庫。請按照以下步驟操作：

   1. 登錄到 PostgreSQL：
      ```bash
      psql -U postgres
      ```

   2. 創建數據庫：
      ```sql
      CREATE DATABASE kg_db;
      ```

   3. 創建用戶並設置密碼：
      ```sql
      CREATE USER kg_user WITH PASSWORD 'kg_pass';
      ```

   4. 授予用戶對數據庫的所有權限：
      ```sql
      GRANT ALL PRIVILEGES ON DATABASE kg_db TO kg_user;
      ```

   5. 創建 `html_content` 表：
      ```sql
      CREATE TABLE html_content (
          id SERIAL PRIMARY KEY,  -- 唯一 ID，自動增長
          filename VARCHAR(255) UNIQUE NOT NULL,  -- 檔名
          content TEXT NOT NULL,  -- HTML 存放原始碼
          metadata JSON,  -- 附加的元數據
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 創建時間
      );
      ```

   6. 退出 PostgreSQL：
      ```sql
      \q
      ```

   確保在 `.env` 文件中使用相同的用戶名和密碼配置數據庫連接。

[服務啟動]
# 開發模式
uvicorn kg_service:app --reload --port 8000

# 生產模式 (4 workers)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker kg_service:app

[API 端點]
1. POST /generate   - 生成知識圖譜並選擇輸出方式
2. GET  /contents   - 查詢所有存儲記錄
3. GET  /content/{id} - 獲取特定內容
4. DELETE /content/{id} - 刪除記錄

[範例調用]
# === API調用範例 ===
# 雙重存儲模式：
#   curl -X POST \
#     -F "input_file=@data.txt" \
#     -F "metadata='{\"project\":\"AI研究\"}'" \
#     -H "X-API-Key: your_key" \
#     http://localhost:8000/generate?output_mode=both

# • 純文件輸出模式：
#   curl -X POST \
#     -F "input_file=@data.txt" \
#     http://localhost:8000/generate

# • 數據庫專用模式：
#   curl -X POST \
#     -F "input_file=@data.txt" \
#     -H "X-API-Key: your_key" \
#     http://localhost:8000/generate?output_mode=db

[安全限制]
1. 輸入文件大小限制：≤10MB
2. 輸出目錄權限：700
3. 數據庫連接池：max 20 connections

[環境配置]
• 新建.env文件(勿提交至版本控制)：
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=kg_db
  DB_USER=kg_service
  DB_PASS=your_strong_password  # 需定期輪換
  MAX_CONTENT_SIZE=10485760     # 10MB限制
  API_KEY=prod_key_!123@        # 生產環境專用
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import subprocess
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from enum import Enum
from dotenv import load_dotenv

# 從環境變量加載配置
load_dotenv()
MAX_CONTENT = int(os.getenv('MAX_CONTENT_SIZE', 10_485_760))

# 數據庫配置
DATABASE_URL = "postgresql://kg_user:kg_pass@localhost/kg_db"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class HTMLContent(Base):
    __tablename__ = "html_content"
    
    id = Column(Integer, primary_key=True, index=True)  # 唯一 ID
    filename = Column(String(255), unique=True, nullable=False)  # 檔名
    content = Column(String, nullable=False)  # HTML 存放原始碼
    metadata = Column(JSON, nullable=True)  # 附加的元數據可以為空
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # 創建時間

    def __repr__(self):
        return f"<HTMLContent(id={self.id}, filename={self.filename}, created_at={self.created_at})>"

Base.metadata.create_all(bind=engine)

app = FastAPI()

class OutputMode(str, Enum):
    BOTH = "both"
    DB = "db"
    FILE = "file"

class GenerationRequest(BaseModel):
    output_mode: OutputMode = OutputMode.FILE
    metadata: Optional[dict] = None

@app.post("/generate", summary="生成知識圖譜", description="接收上傳的文件並生成知識圖譜，根據請求的輸出模式將結果存儲到文件系統或數據庫中。")
async def generate_knowledge_graph(
    input_file: UploadFile = File(..., description="上傳的文件"),
    request: GenerationRequest = None
):
    output_path = f"./output/{input_file.filename}"  # 假設輸出路徑
    db_record = None  # 初始化數據庫記錄

    # 文件系統輸出
    if request.output_mode in [OutputMode.FILE, OutputMode.BOTH]:
        # 新增目錄權限檢查
        if not os.access(os.path.dirname(output_path), os.W_OK):
            raise HTTPException(status_code=403, detail="Directory not writable")
        
        # 執行生成命令
        try:
            cmd = f"uv run generate-graph.py {input_file.filename} {output_path}"  # 假設的命令
            subprocess.run(cmd, shell=True, check=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Generation timeout")

    # 數據庫存儲
    if request.output_mode in [OutputMode.DB, OutputMode.BOTH]:
        # 新增內容長度檢查
        with open(output_path, 'r') as f:
            content = f.read()
        
        if len(content) > 10_000_000:  # 10MB限制
            raise HTTPException(status_code=413, detail="Content too large")
        
        db = SessionLocal()
        try:
            db_record = HTMLContent(
                filename=os.path.basename(output_path),  # 檔名
                content=content,                          # HTML 存放原始碼
                metadata=request.metadata                 # 附加的元數據
            )
            db.add(db_record)
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            db.close()

    # 新增混合模式結果驗證
    if request.output_mode == OutputMode.BOTH:
        if not (os.path.exists(output_path) and db_record.id):
            raise HTTPException(status_code=500, detail="Dual write failed")

    return {
        "file_path": os.path.abspath(output_path) if request.output_mode in [OutputMode.FILE, OutputMode.BOTH] else None,
        "db_id": db_record.id if request.output_mode in [OutputMode.DB, OutputMode.BOTH] else None
    }
