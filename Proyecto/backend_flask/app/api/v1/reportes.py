"""Borrador de endpoints de reportes. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, request
from app.api.v1.responses import pendiente
from app.security.gateway import requiere_usuario

bp = Blueprint("reportes", __name__)


@bp.route("/reportes/resumen", methods=['GET'])
@requiere_usuario
def resumen_reportes():
    return pendiente("reportes", request.method + " /reportes/resumen")


@bp.route("/reportes/predios/<int:predio_id>/historial", methods=['GET'])
@requiere_usuario
def historial_predio(predio_id):
    return pendiente("reportes", request.method + " /reportes/predios/<int:predio_id>/historial")
