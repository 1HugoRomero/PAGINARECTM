"""Borrador de endpoints de predicciones. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, request
from app.api.v1.responses import pendiente
from app.security.gateway import requiere_usuario

bp = Blueprint("predicciones", __name__)


@bp.route("/predicciones/rendimiento", methods=['POST'])
@requiere_usuario
def estimar_rendimiento():
    return pendiente("predicciones", request.method + " /predicciones/rendimiento")
