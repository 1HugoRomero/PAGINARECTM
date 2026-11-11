"""Registra las rutas públicas de la versión 1."""

from app.api.v1 import (
    health,
    auth,
    usuarios,
    predios,
    potreros,
    cultivos,
    insumos,
    zonas,
    temporadas,
    calculos,
    predicciones,
    calendario,
    actividades,
    reportes,
    admin,
    catalogo,
    fertilizantes,
)


def register_v1_blueprints(app):
    for module in (
        health,
        auth,
        usuarios,
        predios,
        potreros,
        cultivos,
        insumos,
        zonas,
        temporadas,
        calculos,
        predicciones,
        calendario,
        actividades,
        reportes,
        admin,
        catalogo,
        fertilizantes,
    ):
        app.register_blueprint(module.bp, url_prefix="/api/v1")
