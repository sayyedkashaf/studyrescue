"""
Pydantic v2 schemas for request/response validation.
Expanded in later phases; this file starts with the health-check response.
"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app_name: str
    database: str
