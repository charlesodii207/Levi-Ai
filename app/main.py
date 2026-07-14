from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine

# Import all database models
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.memory import Memory

# Import API routers
from app.api.users import router as user_router
from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.memory import router as memory_router

# Create all database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Levi AI",
    version="1.0.0",
    description="Premium AI Assistant"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://levi-ai-frontend.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(user_router)
app.include_router(chat_router)
app.include_router(conversation_router)
app.include_router(memory_router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }

    for path_name, path in schema["paths"].items():
        if path_name == "/":
            continue
        for method in path.values():
            method["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
def root():
    return {
        "name": "Levi AI",
        "creator": "Charles Odii Okechukwu",
        "created": "22 June 2026",
        "status": "Backend running successfully!"
    }
