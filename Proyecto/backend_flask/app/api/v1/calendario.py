"""Borrador de endpoints de calendario. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, request
from app.api.v1.responses import pendiente
from app.security.gateway import requiere_usuario

bp = Blueprint("calendario", __name__)


@bp.route("/calendario", methods=['GET'])
@requiere_usuario
def consultar_calendario():
    return pendiente("calendario", request.method + " /calendario")
