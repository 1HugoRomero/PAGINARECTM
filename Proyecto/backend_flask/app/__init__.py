"""Punto de entrada de la API Flask de AgroAsesor (servicio interno detrás de Django)."""

from flask import Flask, redirect, render_template, request
from app.api.v1 import register_v1_blueprints
from app.db import cerrar_bd
from app.errors import register_error_handlers


def create_app(test_config=None):
    """Construye la aplicación. La base (solo lectura) se abre bajo demanda, nunca aquí."""
    app = Flask(__name__)
    app.config.from_object("app.config.Config")
    if test_config is not None:
        app.config.update(test_config)
    app.json.sort_keys = False  # conserva el orden N, P2O5, K2O, MgO, S en las respuestas
    register_v1_blueprints(app)
    register_error_handlers(app)
    app.teardown_appcontext(cerrar_bd)

    @app.after_request
    def cabeceras_seguras(respuesta):
        """Cabeceras defensivas. No se agrega CORS: el navegador solo llega a la API a través de Django."""
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.headers.get("X-AgroAsesor-User"):
            respuesta.headers["Cache-Control"] = "no-store"  # datos de un agricultor: nunca en caché compartida
        return respuesta

    @app.get("/catalogo")
    def catalogo_demo():
        """Vista de demostración independiente, sin modificar Django."""
        return render_template("catalogo.html")

    @app.get("/consola")
    def consola():
        """Consola para probar los endpoints públicos y ver sus respuestas JSON."""
        return render_template("consola.html")

    @app.get("/")
    def inicio():
        return redirect("/consola")

    return app
