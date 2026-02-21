from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import Response, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone

# Import generator
from generator.models import MicroserviceConfig
from generator.engine import MicroserviceGenerator


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks


# ==================== MICROSERVICE GENERATOR ENDPOINTS ====================

generator = MicroserviceGenerator()


@api_router.post("/generate")
async def generate_microservice(config: MicroserviceConfig):
    """
    Generate a complete production-ready microservice
    
    Returns a ZIP file containing all generated code and configuration
    """
    try:
        logger.info(f"Generating microservice: {config.metadata.name}")
        
        # Generate microservice
        zip_bytes = generator.generate(config)
        
        logger.info(f"Successfully generated microservice: {config.metadata.name}")
        
        # Return ZIP file
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={config.metadata.name}.zip"
            }
        )
    
    except Exception as e:
        logger.error(f"Failed to generate microservice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/generator/info")
async def generator_info():
    """Get information about the generator"""
    return {
        "name": "Maximal Microservice Generator",
        "version": "1.0.0",
        "supported_languages": [
            {
                "id": "python_fastapi",
                "name": "Python + FastAPI",
                "status": "available"
            },
            {
                "id": "go_fiber",
                "name": "Go + Fiber",
                "status": "coming_soon"
            },
            {
                "id": "nodejs_nestjs",
                "name": "Node.js + NestJS",
                "status": "coming_soon"
            },
            {
                "id": "rust_actix",
                "name": "Rust + Actix",
                "status": "coming_soon"
            }
        ],
        "features": [
            "Full CI/CD pipeline (GitHub Actions + GitLab CI)",
            "Complete Kubernetes manifests (Deployment, Service, HPA, PDB, NetworkPolicy)",
            "Prometheus metrics with proper cardinality control",
            "Health checks (liveness, readiness, startup)",
            "Security (Authentication, Authorization, Rate Limiting)",
            "Database migrations and management scripts",
            "Comprehensive documentation",
            "Failure mode matrix",
            "SBOM generation",
            "Container image signing",
            "85%+ test coverage requirement",
            "Security scanning (Trivy, Bandit, Gitleaks)",
            "Structured JSON logging",
            "Graceful shutdown",
            "Zero-downtime deployments"
        ]
    }

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()