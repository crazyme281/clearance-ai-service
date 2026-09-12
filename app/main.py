from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.features.assistant.router import router as assistant_router

config.validate_config()

app = FastAPI(
    title="SmartClearX AI Service",
    description="Tool-calling AI assistant for the SmartClearX clearance system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assistant_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "SmartClearX AI Service is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# For AWS Lambda deployment via API Gateway (see README) — harmless if unused.
handler = None
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    pass
