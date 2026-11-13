"""Borrador de endpoints de calculos. Sin acceso a datos reales; exige la autenticación de Django antes de responder 501."""

from flask import Blueprint, g, jsonify, request

from app.api.v1.responses import pendiente
from app.security.gateway import requiere_usuario
from app.services import terreno

bp = Blueprint("calculos", __name__)


@bp.get("/calculos")
@requiere_usuario
def historial():
    """Historial de cálculos del usuario (lectura). Filtro opcional ?potrero_id=."""
    limite = min(max(request.args.get("limite", 50, type=int), 1), 200)
    return jsonify(
        {"calculos": terreno.historial_calculos(g.usuario, request.args.get("potrero_id", type=int), limite)}
    )


@bp.route("/calculos/semillas", methods=['POST'])
@requiere_usuario
def calcular_semillas():
    return pendiente("calculos", request.method + " /calculos/semillas")


@bp.route("/calculos/fertilizantes", methods=['POST'])
@requiere_usuario
def calcular_fertilizantes():
    return pendiente("calculos", request.method + " /calculos/fertilizantes")


@bp.route("/calculos/cobertura", methods=['POST'])
@requiere_usuario
def calcular_cobertura():
    return pendiente("calculos", request.method + " /calculos/cobertura")
