"""Borrador de endpoints de temporadas. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, request
from app.api.v1.responses import pendiente
from app.security.gateway import requiere_usuario

bp = Blueprint("temporadas", __name__)


@bp.route("/temporadas", methods=['GET', 'POST'])
@requiere_usuario
def listar_o_crear_temporadas():
    return pendiente("temporadas", request.method + " /temporadas")


@bp.route("/temporadas/<int:temporada_id>", methods=['GET', 'PATCH', 'DELETE'])
@requiere_usuario
def detalle_temporada(temporada_id):
    return pendiente("temporadas", request.method + " /temporadas/<int:temporada_id>")
