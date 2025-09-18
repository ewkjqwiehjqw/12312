from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from pathlib import Path
from dotenv import load_dotenv
from starlette.middleware.gzip import GZipMiddleware

# Load environment variables from .env file (if present)
load_dotenv()

# Import database and models
from database import create_tables

# Create FastAPI app WITHOUT docs
app = FastAPI(
    title="Grillz Studio",
    docs_url=None,  # Disable /docs
    redoc_url=None,  # Disable /redoc
    openapi_url=None  # Disable /openapi.json
)

# Add gzip compression for responses larger than 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS middleware - RESTRICTED for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "https://grillzstudio.com"],  # Only allow specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Only allow necessary methods
    allow_headers=["Content-Type", "Authorization"],  # Only allow necessary headers
)

class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, request):
        response = await super().get_response(path, request)
        # Cache static assets in the browser for 1 year
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

# Mount static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", CachedStaticFiles(directory=str(static_path)), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Import routers after app creation
from routes import auth, orders, pages, referrals, admin

# Include routers
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(pages.router)
app.include_router(referrals.router)
app.include_router(admin.router)

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Startup event to create database tables
@app.on_event("startup")
async def startup_event():
    print("Creating database tables...")
    await create_tables()
    print("Database tables created!")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 