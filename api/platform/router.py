from fastapi import APIRouter


# The platform boundary is intentionally empty in WP-0003. Later Work Packages
# add resources here without changing or wrapping the Legacy /api/v1 surface.
router = APIRouter(prefix="/platform/v1", tags=["Platform"])
