"""
知識圖譜生成API

安裝依賴：
    pip install fastapi uvicorn python-multipart

啟動服務：
    uvicorn main:app --reload

測試API：
1. 生成圖譜並寫入文件系統：
    curl -X POST "http://localhost:8000/generate-graph" \
         -H "Content-Type: application/json" \
         -d '{"input_file":"your_text_file.txt"}'

2. 儲存HTML到資料庫：
    curl -X POST "http://localhost:8000/store-html" \
         -H "Content-Type: application/json" \
         -d '{"html_content": "<html>...</html>", "filename": "graph_123.html"}'

3. 查詢已儲存記錄(新增GET API)：
    curl "http://localhost:8000/html-contents/1"
"""

# 新增查詢端點
@app.get("/html-contents/{content_id}",
         response_model=HTMLContent,
         summary="取得儲存的HTML內容",
         responses={
             404: {"description": "找不到指定內容"}
         })
async def get_html_content(content_id: int):
    db = SessionLocal()
    content = db.query(HTMLContent).filter(HTMLContent.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    return content

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import subprocess
from pydantic_settings import BaseSettings

# 更新為PostgreSQL配置
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg2://user:password@localhost/knowledge_graph"
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_size=10, max_overflow=20)

# 新增PostgreSQL專用類型(可選)
from sqlalchemy.dialects.postgresql import JSONB

class HTMLContent(Base):
    __tablename__ = "html_contents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, unique=True, comment='儲存的HTML檔案名稱，包含副檔名')
    content = Column(Text, nullable=False)
    metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# 更新請求模型
class HTMLRequest(BaseModel):
    html_content: str
    filename: str = Field(..., min_length=3, example="report_2023.html")

# 更新API端點
app = FastAPI(
    title="知識圖譜生成API",
    description="""
    ## Swagger UI訪問路徑
    - 互動式文檔: http://localhost:8000/docs
    - OpenAPI規格: http://localhost:8000/openapi.json
    """,
    version="1.1.0"
)

@app.post(
    "/store-html",
    tags=["Database API"],
    responses={
        200: {"description": "HTML儲存成功", "content": {"application/json": {"example": {"id": 1, "filename": "report.html"}}}},
        500: {"description": "伺服器內部錯誤"}
    },
    openapi_extra={
        "x-swagger-router-controller": "knowledge_graph"
    }
)
async def store_html(request: HTMLRequest):
    db = SessionLocal()
    try:
        html_record = HTMLContent(
            content=request.html_content,
            filename=request.filename
        )
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
@app.post("/generate-graph")
async def generate_graph(request: GraphRequest):
    output_path = Path(config.HTML_OUTPUT_DIR) / f"graph_{uuid.uuid4()}.html"
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
