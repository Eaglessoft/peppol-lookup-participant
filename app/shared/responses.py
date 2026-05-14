from pydantic import BaseModel, Field


class ApiInfoResponse(BaseModel):
    service: str
    version: str
    status: str
    endpoints: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None

