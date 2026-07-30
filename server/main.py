from fastapi import FastAPI

from server.config import SERVICE_NAME, get_app_configuration_status
from server.database import init_db
from server.routers import auth, jobs, matches, public, rooms


app = FastAPI(title="Neko Block Blast API")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "neko-block-blast-api",
    }


@app.get("/version")
def version_check():
    return {
        "deploy_from": "github-actions",
        "version": "ci-cd-test-01",
    }


@app.get("/config/status")
def config_status():
    return get_app_configuration_status()


app.router.routes.extend(auth.router.routes)
app.router.routes.extend(rooms.router.routes)
app.router.routes.extend(matches.router.routes)
app.router.routes.extend(jobs.router.routes)
app.include_router(public.router)
