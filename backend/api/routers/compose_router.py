from fastapi import APIRouter, HTTPException
from typing import Optional

from ...config import get_config
from ...migration_service import MigrationService

router = APIRouter(
    prefix="/api/compose",
    tags=["Compose"],
)

config = get_config()
migration_service = MigrationService()


@router.get("/stacks")
async def list_compose_stacks():
    """List available Docker Compose stacks with path validation"""
    try:
        stacks = await migration_service.get_compose_stacks()
        return {"stacks": stacks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stacks/{stack_name}")
async def analyze_compose_stack(stack_name: str):
    """Analyze a compose stack with security validation"""
    try:
        stack_info = await migration_service.get_stack_info(stack_name)
        return stack_info
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e 