"""Borrador de endpoints de actividades. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, request
from app.api.v1.responses import pendiente
from app.security.gateway import requiere_usuario

bp = Blueprint("actividades", __name__)


@bp.route("/actividades", methods=['GET', 'POST'])
@requiere_usuario
def listar_o_crear_actividades():
    return pendiente("actividades", request.method + " /actividades")


@bp.route("/actividades/<int:actividad_id>", methods=['GET', 'PATCH', 'DELETE'])
@requiere_usuario
def detalle_actividad(actividad_id):
    return pendiente("actividades", request.method + " /actividades/<int:actividad_id>")
