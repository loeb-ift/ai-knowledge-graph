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
import subprocess
from pydantic import BaseModel

# 初始化FastAPI應用
app = FastAPI(title="Knowledge Graph Generator")

class GraphRequest(BaseModel):
    """請求數據模型
    Attributes:
        input_file: 輸入文本文件路徑 (必填)
        output_file: 輸出HTML文件路徑 (可選，預設為knowledge_graph.html)
    """
    input_file: str
    output_file: str = "knowledge_graph.html"

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
