"""API pública del catálogo de fertilizantes (solo lectura y cálculos sin guardar nada)."""

from flask import Blueprint, jsonify, request

from app.services import fertilizantes as svc

bp = Blueprint("fertilizantes", __name__)


def _error(exc, status=400):
    return jsonify({"error": {"codigo": "VALIDACION_FERTILIZANTES", "mensaje": str(exc)}}), status


def _json():
    if not request.is_json:
        return None, (jsonify({"error": {"codigo": "TIPO_CONTENIDO", "mensaje": "Se requiere application/json"}}), 415)
    return request.get_json(silent=True), None


@bp.get("/catalogo/fertilizantes/resumen")
def resumen():
    return jsonify(svc.resumen())


@bp.get("/catalogo/fertilizantes")
def listar():
    try:
        return jsonify(
            svc.listar(
                q=request.args.get("q", ""),
                nutriente=request.args.get("nutriente", ""),
                grupo=request.args.get("grupo", ""),
            )
        )
    except svc.FertilizanteError as exc:
        return _error(exc)


@bp.get("/catalogo/fertilizantes/<string:fert_id>")
def detalle(fert_id):
    ficha = svc.detalle(fert_id)
    if ficha is None:
        return jsonify({"error": {"codigo": "NO_ENCONTRADO", "mensaje": "Fertilizante no encontrado"}}), 404
    return jsonify(ficha)


@bp.post("/catalogo/calcular-fertilizante")
def calcular():
    payload, error = _json()
    if error:
        return error
    try:
        return jsonify(svc.calcular(payload))
    except svc.FertilizanteError as exc:
        return _error(exc)


@bp.get("/catalogo/conversiones")
def conversiones():
    return jsonify(svc.conversiones())


@bp.get("/catalogo/convertir")
def convertir():
    try:
        return jsonify(svc.convertir(request.args.get("de", ""), request.args.get("a", ""), request.args.get("valor", "")))
    except svc.FertilizanteError as exc:
        return _error(exc)


@bp.get("/catalogo/normativa/contenidos-minimos")
def normativa():
    return jsonify(svc.normativa())


@bp.post("/catalogo/revisar-etiqueta")
def revisar_etiqueta():
    payload, error = _json()
    if error:
        return error
    try:
        return jsonify(svc.revisar_etiqueta(payload))
    except svc.FertilizanteError as exc:
        return _error(exc)
