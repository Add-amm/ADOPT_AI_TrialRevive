"""Passerelle HTTP locale pour le nouveau front, branchée sur NOTRE backend.

Lancer : python server.py [port] (8000 par défaut). Streamlit reste indépendant.
Ni téléchargement de données, ni extraction IA, ni modification de src/ au démarrage.
"""
import json
import logging
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from src import compare, question
import web_adapter

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2_000_000
MAX_QUESTION = 600
logger = logging.getLogger(__name__)


class Json(JSONResponse):
    def render(self, content):
        return json.dumps(web_adapter.json_value(content), ensure_ascii=False, allow_nan=False).encode("utf-8")


class InvalidRequest(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def error(message, status=400):
    return Json({"error": message}, status_code=status)


async def read_json(request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            raise InvalidRequest("Requête trop volumineuse (2 Mo maximum).", 413)
        chunks.append(chunk)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise InvalidRequest("JSON invalide.") from exc
    if not isinstance(payload, dict):
        raise InvalidRequest("Un objet JSON est attendu.")
    return payload


def question_text(value):
    if not isinstance(value, str):
        raise InvalidRequest("La question doit être du texte.")
    text = value.strip()
    if not text:
        raise InvalidRequest("Écrivez une question avant de lancer l'analyse.")
    if len(text) > MAX_QUESTION:
        raise InvalidRequest("La question est trop longue (600 caractères maximum).")
    return text


def baseline_record(value):
    record = compare.validate_record(value)
    if "contexte" in record and not isinstance(record["contexte"], str):
        raise InvalidRequest("Le champ contexte doit être du texte.")
    return record


class LocalResponses(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
        except InvalidRequest as exc:
            response = error(str(exc), exc.status)
        except ValueError as exc:
            response = error(str(exc))
        except Exception:
            logger.exception("Échec de la passerelle web")
            response = error("Service indisponible. Vérifiez la base avec « python -m src.fetch --offline » "
                             "puis « python -m src.cv ».", 503)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-cache"
        # Les liens de sources peuvent être ouverts volontairement. Le site, lui,
        # ne charge ses scripts, polices, images et données que depuis le serveur.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        return response


def create_app(*, baseline_dir=None, analyze=None):
    """Fabrique injectant seulement les accès de bordure pour les tests."""
    baseline_dir = Path(baseline_dir) if baseline_dir is not None else compare.BASELINE_DIR
    analyze = analyze or web_adapter.analyze

    async def info(request):
        return Json({"exemple": question.CAS_VEDETTE_TEXTE})

    async def analyze_route(request):
        payload = await read_json(request)
        text = question_text(payload.get("question", ""))
        return Json(await run_in_threadpool(analyze, text))

    async def dossier_md(request):
        text = question_text(request.query_params.get("question") or question.CAS_VEDETTE_TEXTE)
        result = await run_in_threadpool(analyze, text)
        return Response(result["markdown"], media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="dossier_trialrevive.md"'})

    async def baselines(request):
        records, errors = await run_in_threadpool(compare.load_baselines, baseline_dir)
        valid = []
        for i, record in enumerate(records, 1):
            try:
                valid.append(baseline_record(record))
            except ValueError as exc:
                errors.append(f"Réponse archivée n°{i} : {exc}")
        return Json({"records": valid, "errors": errors})

    async def validate_baseline(request):
        payload = await read_json(request)
        text = payload.get("text")
        if not isinstance(text, str):
            raise InvalidRequest("Le champ text doit contenir le JSON de la réponse.")
        return Json({"record": baseline_record(compare.parse_record(text.lstrip("\ufeff")))})

    async def archive_baseline(request):
        payload = await read_json(request)
        record = baseline_record(payload.get("record"))
        path = await run_in_threadpool(compare.archive_record, record, baseline_dir)
        return Json({"archive": path.name})

    async def comparison(request):
        payload = await read_json(request)
        record = baseline_record(payload.get("record"))
        text = question_text(payload.get("question", question.CAS_VEDETTE_TEXTE))
        result = await run_in_threadpool(analyze, text)
        d = result["dossier"]
        nct = await run_in_threadpool(compare.audit_nct_references, record["reponse_ia"])
        return Json({"rows": compare.comparison_rows(d, record),
                     "meme_question": compare.same_question(d["question"], record["question"]), "nct": nct})

    async def index(request):
        return FileResponse(ROOT / "web" / "index.html")

    async def http_error(request, exc):
        message = "Route introuvable." if exc.status_code == 404 else "Méthode HTTP non autorisée."
        return error(message, exc.status_code)

    app = Starlette(routes=[
        Route("/", index),
        Route("/api/info", info),
        Route("/api/analyze", analyze_route, methods=["POST"]),
        Route("/api/dossier.md", dossier_md),
        Route("/api/baselines", baselines),
        Route("/api/baselines/validate", validate_baseline, methods=["POST"]),
        Route("/api/baselines/archive", archive_baseline, methods=["POST"]),
        Route("/api/compare", comparison, methods=["POST"]),
        Mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets"),
    ], exception_handlers={404: http_error, 405: http_error})
    app.add_middleware(LocalResponses)
    return app


app = create_app()


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port)
