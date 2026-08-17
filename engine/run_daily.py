"""
=============================================================================
 EJECUCION DIARIA  --  se lanza sola desde GitHub Actions
=============================================================================

 Cada dia, tras el cierre del mercado americano, este script:

   1. Descarga los precios actualizados de todo el universo
   2. Comprueba el regimen de mercado (SPY sobre su SMA200)
   3. Busca las senyales de entrada para la apertura siguiente
   4. Actualiza la CARTERA FANTASMA: cierra lo que toca, abre lo nuevo
   5. Recalcula las metricas del sistema con el backtest completo
   6. Escribe public/data/results.json, que es lo que lee la web

 La cartera fantasma vive en public/data/portfolio.json. Es dinero
 ficticio, pero las ejecuciones usan precios reales de mercado.
=============================================================================
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

from backtest_v1 import (
    CONFIG, Backtest, preparar_indicadores,
    obtener_universo, descargar,
)

RAIZ = os.path.join(os.path.dirname(__file__), "..")
DIR_DATOS = os.path.join(RAIZ, "public", "data")
RUTA_CARTERA = os.path.join(DIR_DATOS, "portfolio.json")
RUTA_RESULTADOS = os.path.join(DIR_DATOS, "results.json")

INICIO_HISTORICO = "2015-01-01"


# ---------------------------------------------------------------------------
#  Cartera fantasma: persistencia
# ---------------------------------------------------------------------------

def cargar_cartera():
    if os.path.exists(RUTA_CARTERA):
        with open(RUTA_CARTERA, encoding="utf-8") as f:
            c = json.load(f)
        if not c.get("es_demo"):
            return c
    # Primera ejecucion: cartera limpia
    return {
        "es_demo": False,
        "capital_inicial": CONFIG["capital_inicial"],
        "cash": CONFIG["capital_inicial"],
        "posiciones": {},
        "cerradas": [],
        "historico_equity": [],
    }


def guardar_cartera(c):
    with open(RUTA_CARTERA, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
#  Actualizacion de la cartera fantasma
# ---------------------------------------------------------------------------

def actualizar_cartera(cartera, datos, senales, fecha_hoy):
    """Procesa salidas primero, luego entradas. Mismas reglas que el backtest."""
    cfg = CONFIG
    com = cfg["comision_pct"]
    slip = cfg["slippage_pct"]

    # ---- 1. SALIDAS -------------------------------------------------------
    for ticker in list(cartera["posiciones"].keys()):
        pos = cartera["posiciones"][ticker]
        d = datos.get(ticker)
        if d is None or len(d) == 0:
            continue

        barra = d.iloc[-1]
        precio_salida, motivo = None, None

        if barra["Low"] <= pos["stop"]:
            precio_salida = min(barra["Open"], pos["stop"])
            motivo = "stop"
        elif bool(barra["senal_salida"]):
            precio_salida, motivo = float(barra["Close"]), "objetivo"
        elif pos["dias"] >= cfg["max_dias_posicion"]:
            precio_salida, motivo = float(barra["Close"]), "tiempo"

        if precio_salida is not None:
            p = precio_salida * (1 - slip)
            bruto = p * pos["acciones"]
            cartera["cash"] += bruto - bruto * com
            cartera["cerradas"].append({
                "ticker": ticker,
                "entrada_fecha": pos["fecha"],
                "salida_fecha": fecha_hoy,
                "entrada": round(pos["precio"], 2),
                "salida": round(p, 2),
                "acciones": pos["acciones"],
                "pnl": round((p - pos["precio"]) * pos["acciones"], 2),
                "pnl_pct": round((p / pos["precio"] - 1) * 100, 2),
                "dias": pos["dias"],
                "motivo": motivo,
            })
            del cartera["posiciones"][ticker]
        else:
            pos["dias"] += 1

    # ---- 2. VALORACION ----------------------------------------------------
    equity = cartera["cash"]
    for ticker, pos in cartera["posiciones"].items():
        d = datos.get(ticker)
        precio = float(d.iloc[-1]["Close"]) if d is not None and len(d) else pos["precio"]
        pos["precio_actual"] = round(precio, 2)
        pos["pnl_pct"] = round((precio / pos["precio"] - 1) * 100, 2)
        equity += precio * pos["acciones"]

    # ---- 3. ENTRADAS ------------------------------------------------------
    # Se ejecutan al cierre de hoy como aproximacion de la apertura de manyana.
    huecos = cfg["max_posiciones"] - len(cartera["posiciones"])
    abiertas_hoy = []

    for s in senales[:max(huecos, 0)]:
        ticker = s["ticker"]
        if ticker in cartera["posiciones"]:
            continue
        precio = s["precio_ref"] * (1 + slip)
        riesgo_unit = s["riesgo_unitario"]
        if riesgo_unit <= 0:
            continue

        acciones = int((equity * cfg["riesgo_por_op"]) / riesgo_unit)
        acciones = min(acciones, int((equity * cfg["max_peso_posicion"]) / precio))
        coste = acciones * precio
        coste += coste * com

        if acciones < 1 or coste > cartera["cash"]:
            continue

        cartera["cash"] -= coste
        cartera["posiciones"][ticker] = {
            "fecha": fecha_hoy,
            "precio": round(precio, 2),
            "precio_actual": round(precio, 2),
            "acciones": acciones,
            "stop": round(s["precio_ref"] - riesgo_unit, 2),
            "pnl_pct": 0.0,
            "dias": 0,
        }
        abiertas_hoy.append(ticker)

    # ---- 4. REGISTRO ------------------------------------------------------
    equity = cartera["cash"] + sum(
        p["precio_actual"] * p["acciones"] for p in cartera["posiciones"].values()
    )
    cartera["historico_equity"].append({"d": fecha_hoy, "v": round(equity, 2)})
    cartera["historico_equity"] = cartera["historico_equity"][-500:]
    return cartera, equity, abiertas_hoy


# ---------------------------------------------------------------------------
#  Principal
# ---------------------------------------------------------------------------

def main():
    hoy = datetime.now(timezone.utc)
    print(f"[{hoy:%Y-%m-%d %H:%M}] Iniciando ejecucion diaria")

    universo = obtener_universo()
    print(f"  Universo: {len(universo)} valores")

    datos_crudos = descargar(universo, INICIO_HISTORICO, None)
    print(f"  Descargados: {len(datos_crudos)} con historico suficiente")

    benchmark = descargar(["SPY"], INICIO_HISTORICO, None)["SPY"]

    # --- Regimen de mercado ---
    spy_close = float(benchmark["Close"].iloc[-1])
    spy_sma200 = float(benchmark["Close"].rolling(200).mean().iloc[-1])
    regimen_ok = spy_close > spy_sma200
    print(f"  SPY {spy_close:.2f} vs SMA200 {spy_sma200:.2f} -> "
          f"{'ALCISTA' if regimen_ok else 'BAJISTA'}")

    # --- Indicadores y senyales de hoy ---
    datos = {t: preparar_indicadores(d, CONFIG) for t, d in datos_crudos.items()}
    fecha_hoy = str(benchmark.index[-1].date())

    senales = []
    if regimen_ok:
        for ticker, d in datos.items():
            fila = d.iloc[-1]
            if bool(fila["senal_entrada"]) and not pd.isna(fila["roc"]):
                riesgo_unit = CONFIG["atr_multiplo_stop"] * float(fila["atr"])
                senales.append({
                    "ticker": ticker,
                    "precio_ref": float(fila["Close"]),
                    "riesgo_unitario": riesgo_unit,
                    "stop": round(float(fila["Close"]) - riesgo_unit, 2),
                    "rsi": round(float(fila["rsi"]), 1),
                    "atr": round(float(fila["atr"]), 2),
                    "roc": round(float(fila["roc"]), 1),
                })
        senales.sort(key=lambda x: x["roc"], reverse=True)
    print(f"  Senyales encontradas: {len(senales)}")

    # --- Cartera fantasma ---
    cartera = cargar_cartera()
    cartera, equity, abiertas = actualizar_cartera(cartera, datos, senales, fecha_hoy)
    guardar_cartera(cartera)
    print(f"  Cartera: {equity:,.2f} | abiertas hoy: {abiertas or 'ninguna'}")

    # --- Backtest completo para metricas del sistema ---
    print("  Ejecutando backtest historico...")
    bt = Backtest(datos_crudos, benchmark, CONFIG)
    metricas, curva, _ = bt.ejecutar(benchmark.index)

    curva_muestreada = [
        {"d": str(f.date()), "v": round(float(v), 2)}
        for f, v in curva.resample("W").last().dropna().items()
    ]

    bh = float(benchmark["Close"].iloc[-1] / benchmark["Close"].iloc[0] - 1) * 100

    # --- Enriquecer senyales con el tamanyo sugerido ---
    for s in senales:
        acciones = int((equity * CONFIG["riesgo_por_op"]) / s["riesgo_unitario"])
        acciones = min(acciones, int((equity * CONFIG["max_peso_posicion"]) / s["precio_ref"]))
        s["acciones"] = max(acciones, 0)
        s["importe"] = round(acciones * s["precio_ref"], 2)
        s["riesgo_eur"] = round(acciones * s["riesgo_unitario"], 2)
        s["precio_ref"] = round(s["precio_ref"], 2)
        s.pop("riesgo_unitario")

    salida = {
        "generado": hoy.isoformat(),
        "fecha_datos": fecha_hoy,
        "es_demo": False,
        "regimen": {
            "alcista": bool(regimen_ok),
            "spy": round(spy_close, 2),
            "sma200": round(spy_sma200, 2),
            "distancia_pct": round((spy_close / spy_sma200 - 1) * 100, 2),
        },
        "senales": senales[:10],
        "cartera": {
            "equity": round(equity, 2),
            "cash": round(cartera["cash"], 2),
            "capital_inicial": cartera["capital_inicial"],
            "retorno_pct": round(
                (equity / cartera["capital_inicial"] - 1) * 100, 2),
            "posiciones": [
                {"ticker": t, **p} for t, p in cartera["posiciones"].items()
            ],
            "cerradas": cartera["cerradas"][-20:][::-1],
            "curva": cartera["historico_equity"],
        },
        "metricas": metricas,
        "buy_and_hold_spy": round(bh, 1),
        "curva_backtest": curva_muestreada,
        "universo": len(datos_crudos),
    }

    os.makedirs(DIR_DATOS, exist_ok=True)
    with open(RUTA_RESULTADOS, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    print(f"  Escrito {RUTA_RESULTADOS}")
    print("Listo.")


if __name__ == "__main__":
    main()
