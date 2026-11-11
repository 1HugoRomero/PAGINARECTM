"""Borrador de endpoints de admin. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, request
from app.api.v1.responses import pendiente
from app.security.gateway import requiere_admin

bp = Blueprint("admin", __name__)


@bp.route("/admin/resumen", methods=['GET'])
@requiere_admin
def resumen_administrador():
    return pendiente("admin", request.method + " /admin/resumen")
