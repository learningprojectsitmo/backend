from fastapi import APIRouter

from src.api.v1.endpoints.auth import auth_router
from src.api.v1.endpoints.user import user_router
from src.api.v1.endpoints.project import project_router
from src.api.v1.endpoints.resume import resume_router


routers = APIRouter(prefix="/v1")
router_list = [auth_router, user_router, resume_router, project_router]

for router in router_list:
    router.tags = routers.tags.append("v1")
    routers.include_router(router)
