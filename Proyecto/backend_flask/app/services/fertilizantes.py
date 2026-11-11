"""Catálogo de fertilizantes con composición referencial y fuente citada.

Lee data/fertilizantes.yaml (sin ejecutar código) y valida que cada dato tenga fuente. Ofrece:
- consulta de fertilizantes con N, P2O5, K2O, MgO y S por separado, distinguiendo «0» de «no informado»;
- cálculo de cuánto producto cubre un requerimiento de nutriente que entrega el usuario;
- conversión P2O5 <-> P y K2O <-> K con los factores de la guía FAO/IFA;
- revisión de los CONTENIDOS MÍNIMOS de una etiqueta según la Resolución SAG 8.651/2024 (no del cumplimiento
  normativo completo: contaminantes, patógenos y etiquetado dependen de cuadros y análisis que la API no tiene).

No recomienda dosis: el requerimiento lo ingresa el usuario (análisis de suelo o asesoría técnica).
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
import re
import unicodedata

import yaml

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "fertilizantes.yaml"
ESTADOS = {"cotejada_con_fuente", "citada_sin_cotejar"}
HOSTS_FUENTE = {"www.fertilizer.org", "agris.fao.org", "www.diariooficial.interior.gob.cl"}
COLUMNAS_FUENTE = ("N", "P2O5", "K2O", "Mg", "S")
NUTRIENTES_API = ("N", "P2O5", "K2O", "MgO", "S")
OXIDOS_SAG = ("N", "P2O5", "K2O", "MgO", "CaO", "SO3", "Na2O")
OTROS_SAG = ("carbono_organico", "materia_seca_solidos")
REGLAS_SAG = {"al_menos_uno", "subgrupo_por_cantidad", "todos", "cada_declarado", "sin_minimos"}
MAX_SUPERFICIE_HA = Decimal(100000)
MAX_REQUERIMIENTO = Decimal(2000)
MAX_PESO_SACO = Decimal(1000)


class FertilizanteError(ValueError):
    pass


def _norm(text):
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).casefold()


def _dec(valor):
    return Decimal(str(valor))


def _rango(valor):
    """(mínimo, máximo) en Decimal para un número o un [mín, máx]; None si la fuente no informa el valor."""
    if valor is None:
        return None
    if isinstance(valor, list):
        if len(valor) != 2:
            raise RuntimeError("Un rango debe tener mínimo y máximo")
        bajo, alto = _dec(valor[0]), _dec(valor[1])
    else:
        bajo = alto = _dec(valor)
    if not (Decimal(0) <= bajo <= alto <= Decimal(100)):
        raise RuntimeError("Porcentaje fuera de 0-100 o rango invertido")
    return bajo, alto


def _url_valida(url):
    u = urlparse(url or "")
    return u.scheme == "https" and u.hostname in HOSTS_FUENTE


@lru_cache(maxsize=1)
def cargar():
    """Lee y valida el archivo; un dato sin fuente o mal formado impide arrancar la API."""
    with DATA_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    for campo in ("fuentes", "nutrientes", "grupos", "fertilizantes", "conversiones", "normativa_sag_8651"):
        if campo not in data:
            raise RuntimeError(f"Falta sección: {campo}")
    fuentes_ids = set()
    for fuente in data["fuentes"]:
        if not _url_valida(fuente.get("url")) or ("registro_fao" in fuente and not _url_valida(fuente["registro_fao"])):
            raise RuntimeError(f"URL de fuente no admitida: {fuente.get('id')}")
        fuentes_ids.add(fuente["id"])
    if tuple(n["id"] for n in data["nutrientes"]) != NUTRIENTES_API:
        raise RuntimeError("Los nutrientes deben ser N, P2O5, K2O, MgO y S")
    grupos = {g["id"] for g in data["grupos"]}
    vistos = set()
    for fert in data["fertilizantes"]:
        if fert["id"] in vistos or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fert["id"]):
            raise RuntimeError(f"ID de fertilizante duplicado o inválido: {fert['id']}")
        vistos.add(fert["id"])
        if fert["grupo"] not in grupos or fert["fuente_id"] not in fuentes_ids:
            raise RuntimeError(f"Grupo o fuente inexistente: {fert['id']}")
        if not fert.get("ubicacion") or fert.get("estado_verificacion") not in ESTADOS:
            raise RuntimeError(f"Falta ubicación o estado de verificación: {fert['id']}")
        columnas = fert.get("columnas_fuente") or {}
        if tuple(columnas) != COLUMNAS_FUENTE:
            raise RuntimeError(f"Las columnas deben ser exactamente N, P2O5, K2O, Mg, S: {fert['id']}")
        rangos = [_rango(v) for v in columnas.values()]
        if not any(r and r[1] > 0 for r in rangos):
            raise RuntimeError(f"Fertilizante sin ningún nutriente informado: {fert['id']}")
    if data["conversiones"]["fuente_id"] not in fuentes_ids:
        raise RuntimeError("Conversiones sin fuente")
    norma = data["normativa_sag_8651"]
    if norma["fuente_id"] not in fuentes_ids:
        raise RuntimeError("Normativa sin fuente")
    for cat in norma["categorias"]:
        if cat["regla"] not in REGLAS_SAG:
            raise RuntimeError(f"Regla SAG desconocida: {cat['id']}")
        claves = set(cat.get("minimos_primarios_pct", {})) | set(cat.get("un_macronutriente_pct", {}))
        claves |= set(cat.get("varios_macronutrientes_pct", {}))
        if claves - set(OXIDOS_SAG) or set(cat.get("minimos_otros_pct", {})) - set(OTROS_SAG):
            raise RuntimeError(f"Nutriente SAG desconocido en {cat['id']}")
    return data


def _fuentes_por_id():
    return {f["id"]: f for f in cargar()["fuentes"]}


def _num(valor):
    """Número JSON: entero si no tiene decimales."""
    valor = _dec(valor)
    return int(valor) if valor == valor.to_integral_value() else float(valor)


def _r(valor, decimales="0.01"):
    return float(valor.quantize(Decimal(decimales), rounding=ROUND_HALF_UP))


def _txt(bajo, alto):
    """Texto en notación chilena: «16–20» para rangos (guion largo), «46» para valores únicos."""
    fmt = lambda v: str(_num(v)).replace(".", ",")
    return fmt(bajo) if bajo == alto else f"{fmt(bajo)}–{fmt(alto)}"


def _rangos_api(fert):
    """{nutriente: (mín, máx) | None} para N, P2O5, K2O, MgO y S. MgO se calcula desde el Mg de la fuente."""
    columnas = fert["columnas_fuente"]
    factor = _dec(cargar()["factor_mg_a_mgo"])
    salida = {k: _rango(columnas[k]) for k in ("N", "P2O5", "K2O", "S")}
    mg = _rango(columnas["Mg"])
    salida["MgO"] = None if mg is None else (
        _dec(_r(mg[0] * factor, "0.1")),
        _dec(_r(mg[1] * factor, "0.1")),
    )
    return {k: salida[k] for k in NUTRIENTES_API}


def _composicion(fert):
    salida = {}
    columnas = fert["columnas_fuente"]
    for nutriente, rango in _rangos_api(fert).items():
        if rango is None:
            salida[nutriente] = {
                "informado_en_fuente": False,
                "min_pct": None,
                "max_pct": None,
                "es_rango": False,
                "texto": "no informado",
            }
            continue
        bajo, alto = rango
        dato = {
            "informado_en_fuente": True,
            "min_pct": _num(bajo),
            "max_pct": _num(alto),
            "es_rango": bajo != alto,
            "texto": _txt(bajo, alto) + " %",
        }
        if nutriente == "MgO":
            mg = _rango(columnas["Mg"])
            dato["origen"] = "calculado"
            dato["valor_en_fuente"] = {"Mg_pct": _txt(*mg)}
            dato["calculo"] = f"MgO = Mg × {cargar()['factor_mg_a_mgo']} (masas molares IUPAC)"
        else:
            dato["origen"] = "fuente"
        salida[nutriente] = dato
    return salida


def _grado(fert):
    """N, P2O5 y K2O como texto separado; evita «0-16-20-0», que se confunde con un 20 % de K2O."""
    comp = _composicion(fert)
    partes = {k: (comp[k]["texto"].replace(" %", "") if comp[k]["informado_en_fuente"] else "—") for k in ("N", "P2O5", "K2O")}
    return {**partes, "texto": f"N {partes['N']} · P2O5 {partes['P2O5']} · K2O {partes['K2O']}"}


def _ficha(fert):
    return {
        "id": fert["id"],
        "nombre": fert["nombre"],
        "formula": fert.get("formula_fuente"),
        "formula_origen": "fuente" if fert.get("formula_fuente") else "no_indicada_en_fuente",
        "grupo": fert["grupo"],
        "tipo_composicion": "referencial",
        "grado": _grado(fert),
        "composicion_referencial": _composicion(fert),
        "columnas_en_fuente": fert["columnas_fuente"],
        "ubicacion_en_fuente": fert["ubicacion"],
        "estado_verificacion": fert["estado_verificacion"],
        "nota": fert.get("nota"),
        "fuente": _fuentes_por_id()[fert["fuente_id"]],
        "aviso": "Composición referencial publicada por FAO/IFA. Para tu producto vale lo que declara su etiqueta.",
    }


def resumen():
    data = cargar()
    return {
        "version": data["version"],
        "fecha_consulta": data["fecha_consulta"],
        "aviso": data["aviso_general"],
        "nutrientes": data["nutrientes"],
        "grupos": data["grupos"],
        "fuentes": data["fuentes"],
        "total_fertilizantes": len(data["fertilizantes"]),
    }


def listar(q="", nutriente="", grupo=""):
    data = cargar()
    if nutriente and nutriente not in NUTRIENTES_API:
        raise FertilizanteError("Nutriente desconocido. Usa N, P2O5, K2O, MgO o S")
    if grupo and grupo not in {g["id"] for g in data["grupos"]}:
        raise FertilizanteError("Grupo desconocido")
    if len(q) > 100:
        raise FertilizanteError("La búsqueda no puede superar 100 caracteres")
    encontrados = []
    for f in data["fertilizantes"]:
        rango = _rangos_api(f).get(nutriente) if nutriente else None
        if nutriente and not (rango and rango[1] > 0):
            continue
        if grupo and f["grupo"] != grupo:
            continue
        if q and _norm(q) not in _norm(" ".join((f["id"], f["nombre"], f.get("formula_fuente") or ""))):
            continue
        encontrados.append(_ficha(f))
    return {"total": len(encontrados), "resultados": encontrados, "aviso": data["aviso_general"]}


def detalle(fert_id):
    for fert in cargar()["fertilizantes"]:
        if fert["id"] == fert_id:
            return _ficha(fert)
    return None


def _positivo(payload, campo, maximo, requerido=True):
    if campo not in payload:
        if requerido:
            raise FertilizanteError(f"Falta {campo}")
        return None
    valor = payload[campo]
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise FertilizanteError(f"{campo} debe ser un número")
    try:
        dec = _dec(valor)
    except InvalidOperation:
        raise FertilizanteError(f"{campo} inválido")
    if not dec.is_finite() or not (Decimal(0) < dec <= _dec(maximo)):
        raise FertilizanteError(f"{campo} debe ser mayor que cero y no superar {_num(maximo)}")
    return dec


def _min_max(bajo, alto, decimales="0.01"):
    return {"min": _r(bajo, decimales), "max": _r(alto, decimales)}


def calcular(payload):
    """Kilos de producto para aportar el requerimiento indicado por el usuario.

    producto_kg_ha = requerimiento_kg_ha × 100 / ley_%. Si la ley no viene de la etiqueta y la fuente da un rango,
    el resultado es un rango (la ley más alta da la cantidad mínima de producto y viceversa).
    """
    if not isinstance(payload, dict):
        raise FertilizanteError("Enviar un objeto JSON")
    permitidos = {
        "fertilizante_id",
        "nutriente",
        "requerimiento_kg_ha",
        "superficie_ha",
        "superficie_m2",
        "ley_declarada_pct",
        "peso_saco_kg",
    }
    sobrantes = set(payload) - permitidos
    if sobrantes:
        raise FertilizanteError("Campos no admitidos: " + ", ".join(sorted(sobrantes)))
    fert = next((f for f in cargar()["fertilizantes"] if f["id"] == payload.get("fertilizante_id")), None)
    if fert is None:
        raise FertilizanteError("Fertilizante desconocido")
    nutriente = payload.get("nutriente")
    if nutriente not in NUTRIENTES_API:
        raise FertilizanteError("nutriente debe ser N, P2O5, K2O, MgO o S")
    rangos = _rangos_api(fert)
    if not (rangos[nutriente] and rangos[nutriente][1] > 0):
        aporta = [k for k, v in rangos.items() if v and v[1] > 0]
        raise FertilizanteError(
            f"{fert['nombre']} no aporta {nutriente} según la fuente. Aporta: {', '.join(aporta)}"
        )
    if ("superficie_ha" in payload) == ("superficie_m2" in payload):
        raise FertilizanteError("Indica superficie_ha O superficie_m2, no ambas")
    hectareas = (
        _positivo(payload, "superficie_ha", MAX_SUPERFICIE_HA)
        if "superficie_ha" in payload
        else _positivo(payload, "superficie_m2", MAX_SUPERFICIE_HA * 10000) / Decimal(10000)
    )
    requerimiento = _positivo(payload, "requerimiento_kg_ha", MAX_REQUERIMIENTO)
    peso_saco = _positivo(payload, "peso_saco_kg", MAX_PESO_SACO, requerido=False)
    ref_bajo, ref_alto = rangos[nutriente]
    declarada = _positivo(payload, "ley_declarada_pct", 100, requerido=False)
    advertencias = ["El requerimiento lo ingresaste tú: este cálculo no recomienda dosis."]
    if declarada is not None:
        ley_baja = ley_alta = declarada
        ley = {
            "tipo": "declarada_en_etiqueta",
            "valor_pct": _num(declarada),
            "referencia_fuente_pct": _txt(ref_bajo, ref_alto),
        }
        if not (ref_bajo <= declarada <= ref_alto):
            advertencias.append(
                f"La ley de la etiqueta ({_num(declarada)} %) está fuera del rango referencial "
                f"{_txt(ref_bajo, ref_alto)} %: revisa que sea el producto correcto."
            )
    else:
        if ref_bajo == 0:
            raise FertilizanteError(
                f"La referencia de {nutriente} parte en 0 %: indica ley_declarada_pct según la etiqueta"
            )
        ley_baja, ley_alta = ref_bajo, ref_alto
        ley = {
            "tipo": "referencial",
            "valor_pct": _txt(ref_bajo, ref_alto),
            "min_pct": _num(ref_bajo),
            "max_pct": _num(ref_alto),
        }
        advertencias.append(
            "Se usó la composición REFERENCIAL de FAO/IFA porque no indicaste la ley de la etiqueta: "
            "el resultado puede variar con el producto real."
        )
    if fert["estado_verificacion"] != "cotejada_con_fuente":
        advertencias.append("La composición referencial de este producto no está cotejada: confirma con la etiqueta.")

    # Ley alta => menos producto. Por eso el mínimo de producto usa la ley máxima.
    prod_min = requerimiento * 100 / ley_alta
    prod_max = requerimiento * 100 / ley_baja
    aportes = []
    for otro, rango in rangos.items():
        if otro == nutriente or rango is None:
            continue
        aportes.append({"nutriente": otro, **_min_max(prod_min * rango[0] / 100, prod_max * rango[1] / 100)})
    resultado = {
        "fertilizante": {"id": fert["id"], "nombre": fert["nombre"]},
        "nutriente": nutriente,
        "requerimiento_kg_ha": _num(requerimiento),
        "superficie_ha": _r(hectareas, "0.0001"),
        "ley": ley,
        "formula": "producto_kg_ha = requerimiento_kg_ha × 100 / ley_%; total_kg = producto_kg_ha × superficie_ha",
        "producto_kg_ha": _min_max(prod_min, prod_max),
        "producto_total_kg": _min_max(prod_min * hectareas, prod_max * hectareas),
        "aportes_adicionales_kg_ha": aportes,
        "fuente": _fuentes_por_id()[fert["fuente_id"]],
        "ubicacion_en_fuente": fert["ubicacion"],
        "advertencias": advertencias,
    }
    if peso_saco is not None:
        total_min, total_max = prod_min * hectareas, prod_max * hectareas
        sacos_min = int((total_min / peso_saco).to_integral_value(rounding=ROUND_CEILING))
        sacos_max = int((total_max / peso_saco).to_integral_value(rounding=ROUND_CEILING))
        resultado["sacos"] = {
            "peso_saco_kg": _num(peso_saco),
            "cantidad": {"min": sacos_min, "max": sacos_max},
            "sobrante_kg": {"min": _r(peso_saco * sacos_min - total_min), "max": _r(peso_saco * sacos_max - total_max)},
            "nota": "El peso del saco lo indicas tú; no corresponde a un envase comercial verificado.",
        }
    return resultado


def conversiones():
    data = cargar()["conversiones"]
    return {**data, "fuente": _fuentes_por_id()[data["fuente_id"]]}


def convertir(de, a, valor_texto):
    factor = next((c["factor"] for c in cargar()["conversiones"]["factores"] if c["de"] == de and c["a"] == a), None)
    if factor is None:
        raise FertilizanteError("Conversión no disponible. Usa P2O5↔P o K2O↔K")
    try:
        valor = _dec(valor_texto)
    except InvalidOperation:
        raise FertilizanteError("valor debe ser un número")
    if not valor.is_finite() or not (Decimal(0) <= valor <= Decimal(1000000)):
        raise FertilizanteError("valor debe estar entre 0 y 1.000.000")
    return {
        "de": de,
        "a": a,
        "valor": _num(valor),
        "factor": factor,
        "resultado": _r(valor * _dec(factor), "0.0001"),
        "fuente": _fuentes_por_id()[cargar()["conversiones"]["fuente_id"]],
        "ubicacion_en_fuente": cargar()["conversiones"]["ubicacion"],
    }


def normativa():
    data = cargar()["normativa_sag_8651"]
    return {
        **data,
        "fuente": _fuentes_por_id()[data["fuente_id"]],
        "aviso": (
            "Los límites numéricos de los Cuadros N° 1 a 11 (micronutrientes, Cu/Zn, metales pesados y patógenos) "
            "no se transcriben: consulta la resolución publicada."
        ),
    }


def _categoria(cat_id):
    for cat in cargar()["normativa_sag_8651"]["categorias"]:
        if cat["id"] == cat_id:
            return cat
    ids = ", ".join(c["id"] for c in cargar()["normativa_sag_8651"]["categorias"])
    raise FertilizanteError(f"categoria desconocida. Usa: {ids}")


def _porcentaje(dic, clave):
    valor = dic[clave]
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise FertilizanteError(f"{clave} debe ser un número")
    dec = _dec(valor)
    if not dec.is_finite() or not (Decimal(0) < dec <= 100):
        raise FertilizanteError(f"{clave} debe ser mayor que 0 y no superar 100")
    return dec


def revisar_etiqueta(payload):
    """Revisa SOLO los contenidos mínimos de nutrientes (y el biuret si se informa) según la Res. SAG 8.651/2024.

    Formato: {"categoria": "inorganico", "nutrientes": {"N": 46}, "contiene_urea": true, "biuret_pct": 1,
              "otros": {"carbono_organico": 6}, "estado": "solido"}
    También acepta el formato abreviado {"N": 46} (se interpreta como fertilizante inorgánico).
    """
    if not isinstance(payload, dict) or not payload:
        raise FertilizanteError('Envía la categoría y los nutrientes, por ejemplo {"categoria": "inorganico", "nutrientes": {"N": 46}}')
    if "nutrientes" not in payload and "categoria" not in payload:
        payload = {"categoria": "inorganico", "nutrientes": payload}
    permitidos = {"categoria", "nutrientes", "otros", "contiene_urea", "biuret_pct", "estado"}
    if set(payload) - permitidos:
        raise FertilizanteError("Campos no admitidos: " + ", ".join(sorted(set(payload) - permitidos)))
    cat = _categoria(payload.get("categoria"))
    nutrientes_in = payload.get("nutrientes") or {}
    otros_in = payload.get("otros") or {}
    if not isinstance(nutrientes_in, dict) or not isinstance(otros_in, dict):
        raise FertilizanteError("nutrientes y otros deben ser objetos")
    if set(nutrientes_in) - set(OXIDOS_SAG):
        raise FertilizanteError(
            "Nutrientes no admitidos: " + ", ".join(sorted(set(nutrientes_in) - set(OXIDOS_SAG)))
            + ". Usa " + ", ".join(OXIDOS_SAG) + " (como en la norma)"
        )
    if set(otros_in) - set(OTROS_SAG):
        raise FertilizanteError("otros admite solo: " + ", ".join(OTROS_SAG))
    declarados = {k: _porcentaje(nutrientes_in, k) for k in nutrientes_in}
    otros = {k: _porcentaje(otros_in, k) for k in otros_in}
    estado = payload.get("estado", "solido")
    if estado not in {"solido", "liquido"}:
        raise FertilizanteError("estado debe ser solido o liquido")
    contiene_urea = payload.get("contiene_urea", False)
    if not isinstance(contiene_urea, bool):
        raise FertilizanteError("contiene_urea debe ser true o false")

    revisados, observaciones = [], []
    regla = cat["regla"]
    if regla == "sin_minimos":
        observaciones.append("La norma no fija contenidos mínimos de nutrientes para esta categoría.")
        minimos = {}
    elif regla == "subgrupo_por_cantidad":
        if not declarados:
            raise FertilizanteError("Indica al menos un nutriente declarado")
        clave = "un_macronutriente_pct" if len(declarados) == 1 else "varios_macronutrientes_pct"
        observaciones.append(
            "Subgrupo a: un solo macronutriente." if len(declarados) == 1 else "Subgrupo b: dos o más macronutrientes."
        )
        minimos = cat[clave]
    else:
        minimos = cat.get("minimos_primarios_pct", {})
        if regla == "cada_declarado" and not declarados:
            raise FertilizanteError("Indica al menos un nutriente declarado")

    for clave, valor in declarados.items():
        if clave in minimos:
            minimo = _dec(minimos[clave])
            revisados.append({"dato": clave, "declarado_pct": _num(valor), "minimo_pct": _num(minimo), "cumple": valor >= minimo})
        else:
            observaciones.append(f"{clave}: la norma no fija un mínimo transcrito para esta categoría; no se evaluó.")
    if regla in {"al_menos_uno"} and minimos:
        if not any(r["cumple"] for r in revisados if r["dato"] in minimos):
            revisados.append({
                "dato": "nutriente_principal",
                "declarado_pct": None,
                "minimo_pct": None,
                "cumple": False,
                "detalle": "Debe declarar al menos uno de: " + ", ".join(f"{k} ≥ {_num(v)} %" for k, v in minimos.items()),
            })
    for clave, minimo in cat.get("minimos_otros_pct", {}).items():
        if clave == "materia_seca_solidos" and estado == "liquido":
            observaciones.append("Materia seca: no se exige a enmiendas líquidas.")
            continue
        if clave in otros:
            revisados.append({"dato": clave, "declarado_pct": _num(otros[clave]), "minimo_pct": _num(minimo), "cumple": otros[clave] >= _dec(minimo)})
        elif regla == "cada_declarado":
            continue  # en mezclas el carbono orgánico solo se exige si se declara
        else:
            revisados.append({"dato": clave, "declarado_pct": None, "minimo_pct": _num(minimo), "cumple": False, "detalle": "Dato obligatorio no informado"})

    biuret_max = _dec(cargar()["normativa_sag_8651"]["biuret_maximo_pct"])
    if contiene_urea and cat["usa_biuret"]:
        if "biuret_pct" in payload:
            biuret = _porcentaje(payload, "biuret_pct")
            revisados.append({"dato": "biuret", "declarado_pct": _num(biuret), "maximo_pct": _num(biuret_max), "cumple": biuret <= biuret_max})
        else:
            revisados.append({"dato": "biuret", "declarado_pct": None, "maximo_pct": _num(biuret_max), "cumple": False, "detalle": "Si contiene urea debe declarar biuret"})

    norma = normativa()
    return {
        "categoria": {"id": cat["id"], "nombre": cat["nombre"], "ubicacion": cat["ubicacion"]},
        "alcance": "Solo contenidos mínimos de nutrientes" + (" y biuret" if contiene_urea and cat["usa_biuret"] else ""),
        "cumple_contenidos_minimos": all(r["cumple"] for r in revisados) if revisados else None,
        "revisados": revisados,
        "observaciones": observaciones,
        "no_revisado": {
            "contaminantes_a_declarar": cat["contaminantes_a_declarar"],
            "limites_en_cuadros": cat["limites_en_cuadros"],
            "requisitos_especiales": cat["requisitos_especiales"],
            "otros": ["Etiquetado (resolución de etiquetado)", "Micronutrientes (Cuadro N° 1)", "Tolerancias de análisis oficial"],
        },
        "vigencia": norma["vigencia"],
        "fuente": norma["fuente"],
        "aviso": (
            "Esta revisión NO acredita el cumplimiento de la Resolución 8.651: solo compara los contenidos mínimos "
            "de nutrientes declarados. Contaminantes, patógenos y etiquetado requieren análisis y los cuadros de la norma."
        ),
    }
