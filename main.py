"""
知識圖譜生成API

安裝依賴：
    pip install fastapi uvicorn python-multipart

啟動服務：
    uvicorn main:app --reload

測試API：
    curl -X POST "http://localhost:8000/generate-graph" \
         -H "Content-Type: application/json" \
         -d '{"input_file":"your_text_file.txt"}'
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import subprocess

# 更新為PostgreSQL配置
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://user:password@localhost/knowledge_graph"
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_size=10, max_overflow=20)

# 新增PostgreSQL專用類型(可選)
from sqlalchemy.dialects.postgresql import JSONB

class HTMLContent(Base):
    __tablename__ = "html_contents"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    metadata = Column(JSONB)  # 新增JSONB類型欄位
    created_at = Column(DateTime(timezone=True), default=func.now())

Base.metadata.create_all(bind=engine)

app = FastAPI()

class GraphRequest(BaseModel):
    """請求數據模型
    Attributes:
        input_file: 輸入文本文件路徑 (必填)
        output_file: 輸出HTML文件路徑 (可選，預設為knowledge_graph.html)
    """
    input_file: str
    output_file: str = "knowledge_graph.html"

# 新增請求模型
class HTMLRequest(BaseModel):
    html_content: str

# 新增API端點
@app.post("/store-html",
    responses={
        200: {"description": "HTML儲存成功", "content": {"application/json": {"example": {"id": 1, "created_at": "2024-03-01T12:00:00"}}}},
        500: {"description": "伺服器內部錯誤", "content": {"application/json": {"example": {"detail": "錯誤訊息..."}}}}
    },
    summary="儲存HTML內容到資料庫",
    description="""
    ### 測試方法
    ```bash
    curl -X POST "http://localhost:8000/store-html" \
         -H "Content-Type: application/json" \
         -d '{"html_content": "<html>...</html>"}'
    ```
    
    ### 請求參數
    ```json
    {
      "html_content": "<html>...</html>"
    }
    ```
    """
)
async def store_html(request: HTMLRequest):
    db = SessionLocal()
    try:
        html_record = HTMLContent(content=request.html_content)
        db.add(html_record)
        db.commit()
        db.refresh(html_record)
        return {"id": html_record.id, "created_at": html_record.created_at}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.post(
    "/generate-graph",
    summary="生成知識圖譜",
    description="執行generate-graph.py腳本並返回生成結果"
)
async def generate_graph(request: GraphRequest):
    """
    主要處理函數：
    1. 接收並驗證請求參數
    2. 調用子進程執行Python腳本
    3. 處理執行結果與異常
    """
    try:
        # 使用subprocess執行外部指令
        result = subprocess.run(
            [
                "python",
                "generate-graph.py",
                "--input", request.input_file,
                "--output", request.output_file
            ],
            capture_output=True,  # 捕獲標準輸出/錯誤
            text=True,            # 以文本模式返回結果
            check=True            # 自動拋出錯誤當返回碼非零
        )

        # 成功時返回JSON響應
        return {
            "status": "success",
            "message": result.stdout,
            "output_file": request.output_file
        }

    except subprocess.CalledProcessError as e:
        # 處理子進程錯誤
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": f"執行失敗: {e.stderr}",
                "returncode": e.returncode
            }
        )
    except Exception as e:
        # 處理其他未預期錯誤
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": f"系統錯誤: {str(e)}"
            }
        )
