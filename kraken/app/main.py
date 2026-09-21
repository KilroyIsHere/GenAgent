from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import PlainTextResponse
from pathlib import Path
from pydantic import BaseModel
import subprocess
import tempfile
import shutil
import uuid
import torch


app = FastAPI(
    title="Kraken OCR API",
    description="HTTP wrapper around Kraken for Hermes",
    version="1.1"
)

MODEL_DIR = Path("/models")
DATA_DIR = Path("/data")
WORKSPACE_DIR = Path("/workspace")


@app.get("/")
def root():
    return {
        "service": "Kraken OCR",
        "status": "running",
        "default_device": "cpu"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
        "cuda_device": (
            torch.cuda.get_device_name(0)
            if torch.cuda.is_available()
            else None
        ),
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "default_device": "cpu"
    }


@app.get("/models")
def models():
    files = []

    if MODEL_DIR.exists():
        for f in MODEL_DIR.rglob("*"):
            if f.is_file():
                files.append(str(f.relative_to(MODEL_DIR)))

    return {
        "models": files
    }


@app.post("/ocr", response_class=PlainTextResponse)
async def ocr(
    file: UploadFile = File(...),
    model: str = Form(...),
    device: str = Form("cpu"),
    precision: str = Form("32-true"),
    batch_size: int = Form(8),
    line_workers: int = Form(0),
):
    model_path = (MODEL_DIR / model).resolve()

    try:
        model_path.relative_to(MODEL_DIR.resolve())
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Invalid model path"
        )

    if not model_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Model not found: {model}"
        )

    if not model_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Model path is not a file: {model}"
        )

    job_id = str(uuid.uuid4())

    workdir = Path(
        tempfile.mkdtemp(prefix=f"kraken_upload_{job_id}_")
    )

    safe_filename = Path(
        file.filename or "input.jpg"
    ).name

    input_path = workdir / safe_filename
    output_path = workdir / "output.txt"

    try:
        with input_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        cmd = [
            "kraken",
            "-i",
            str(input_path),
            str(output_path),
            "--device",
            device,
            "--precision",
            precision,
            "segment",
            "-bl",
            "ocr",
            "-m",
            str(model_path),
            "-B",
            str(batch_size),
            "--num-line-workers",
            str(line_workers),
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Kraken failed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "command": cmd,
                }
            )

        if not output_path.exists():
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Kraken produced no output file",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "command": cmd,
                    "expected_output": str(output_path),
                }
            )

        return output_path.read_text(
            encoding="utf-8",
            errors="replace"
        )

    finally:
        shutil.rmtree(
            workdir,
            ignore_errors=True
        )


class OCRPathRequest(BaseModel):
    path: str
    model: str

    # CPU defaults
    device: str = "cpu"
    precision: str = "32-true"
    batch_size: int = 8
    line_workers: int = 0


@app.post("/ocr-path", response_class=PlainTextResponse)
def ocr_path(req: OCRPathRequest):

    input_path = Path(req.path).resolve()
    model_path = (MODEL_DIR / req.model).resolve()

    allowed_root = WORKSPACE_DIR.resolve()
    model_root = MODEL_DIR.resolve()

    try:
        input_path.relative_to(allowed_root)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Only files inside /workspace are permitted"
        )

    try:
        model_path.relative_to(model_root)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Invalid model path"
        )

    if not input_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Input file not found: {input_path}"
        )

    if not input_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a file: {input_path}"
        )

    if not model_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Model not found: {req.model}"
        )

    if not model_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Model path is not a file: {req.model}"
        )

    workdir = Path(
        tempfile.mkdtemp(prefix="kraken_path_")
    )

    output_path = workdir / "output.txt"

    try:
        cmd = [
            "kraken",
            "-i",
            str(input_path),
            str(output_path),
            "--device",
            req.device,
            "--precision",
            req.precision,
            "segment",
            "-bl",
            "ocr",
            "-m",
            str(model_path),
            "-B",
            str(req.batch_size),
            "--num-line-workers",
            str(req.line_workers),
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Kraken failed",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "command": cmd,
                }
            )

        if not output_path.exists():
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Kraken produced no output file",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "command": cmd,
                    "expected_output": str(output_path),
                }
            )

        return output_path.read_text(
            encoding="utf-8",
            errors="replace"
        )

    finally:
        shutil.rmtree(
            workdir,
            ignore_errors=True
        )