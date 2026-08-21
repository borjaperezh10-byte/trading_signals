"""
=============================================================================
 EJECUCION DIARIA v2  --  dos carteras fantasma en paralelo
=============================================================================

 CARTERA A - PULLBACK
   La original. Senyales diarias, posiciones de 4-6 dias.
   El backtest dijo que no tiene ventaja; se mantiene viva para
   comprobarlo con precios reales en lugar de fiarnos solo del historico.

 CARTERA B - MOMENTUM
   Rebalanceo cada ~21 sesiones. Mantiene los valores mas fuertes
   mientras sigan liderando. Unas 24 operaciones al anyo.

 Ambas parten de 5.000 EUR ficticios y usan precios reales de mercado.
 En unos meses tendras una comparacion directa que ningun backtest
 puede darte, porque ocurre en datos que no existian al disenyarlas.
=============================================================================
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

from backtest_v1 import CONFIG, obtener_universo, descargar, preparar_indicadores
from momentum import BASE_MOM, construir_paneles

RAIZ = os.path.join(os.path.dirname(__file__), "..")
DIR_DATOS = os.path.join(RAIZ, "public", "data")
RUTA_CARTERAS = os.path.join(DIR_DATOS, "portfolio.json")
RUTA_RESULTADOS = os.path.join(DIR_DATOS, "results.json")

INICIO = "2015-01-01"
CAPITAL = 5000.0
MAX_PESO = 0.25
COM = 0.0010
SLIP = 0.0005


# ---------------------------------------------------------------------------
#  Persistencia
# ---------------------------------------------------------------------------

def cartera_vacia():
    return {"cash": CAPITAL, "capital_inicial": CAPITAL, "posiciones": {},
            "cerradas": [], "historico_equity": [], "ultimo_rebalanceo": None}


def cargar():
    if os.path.exists(RUTA_CARTERAS):
        try:
            with open(RUTA_CARTERAS, encoding="utf-8") as f:
                c = json.load(f)
            if not c.get("es_demo") and "pullback" in c and "momentum" in c:
                return c
        except Exception:
            pass
    return {"pullback": cartera_vacia(), "momentum": cartera_vacia()}


def guardar(c):
    with open(RUTA_CARTERAS, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)


def equity_de(cart, precios_hoy):
    """Valora la cartera y actualiza el precio actual de cada posicion."""
    total = cart["cash"]
    for tk, p in cart["posiciones"].items():
        px = precios_hoy.get(tk)
        px = float(px) if px is not None and pd.notna(px) else p["precio"]
        p["precio_actual"] = round(px, 2)
        p["pnl_pct"] = round((px / p["precio"] - 1) * 100, 2)
        total += px * p["acciones"]
    return total


def registrar(cart, equity, fecha):
    cart["historico_equity"].append({"d": fecha, "v": round(equity, 2)})
    cart["historico_equity"] = cart["historico_equity"][-500:]


def cerrar(cart, tk, pv, fecha, motivo):
    p = cart["posiciones"][tk]
    bruto = pv * p["acciones"]
    cart["cash"] += bruto - bruto * COM
    cart["cerradas"].append({
        "ticker": tk, "entrada_fecha": p["fecha"], "salida_fecha": fecha,
        "entrada": round(p["precio"], 2), "salida": round(pv, 2),
        "acciones": round(p["acciones"], 4),
        "pnl": round((pv - p["precio"]) * p["acciones"], 2),
        "pnl_pct": round((pv / p["precio"] - 1) * 100, 2),
        "dias": (pd.Timestamp(fecha) - pd.Timestamp(p["fecha"])).days,
        "motivo": motivo,
    })
    del cart["posiciones"][tk]


# ---------------------------------------------------------------------------
#  CARTERA A: pullback
# ---------------------------------------------------------------------------

def gestionar_pullback(cart, datos, senales, fecha, precios_hoy):
    for tk in list(cart["posiciones"]):
        p = cart["posiciones"][tk]
        d = datos.get(tk)
        if d is None or len(d) == 0:
            continue
        barra = d.iloc[-1]
        precio, motivo = None, None

        if float(barra["Low"]) <= p["stop"]:
            precio, motivo = min(float(barra["Open"]), p["stop"]), "stop"
        elif bool(barra["senal_salida"]):
            precio, motivo = float(barra["Close"]), "objetivo"
        elif p["dias"] >= CONFIG["max_dias_posicion"]:
            precio, motivo = float(barra["Close"]), "tiempo"

        if precio is not None:
            cerrar(cart, tk, precio * (1 - SLIP), fecha, motivo)
        else:
            p["dias"] += 1

    equity = equity_de(cart, precios_hoy)
    huecos = CONFIG["max_posiciones"] - len(cart["posiciones"])

    for s in senales[:max(huecos, 0)]:
        tk = s["ticker"]
        if tk in cart["posiciones"]:
            continue
        precio = s["_precio"] * (1 + SLIP)
        riesgo_u = s["_riesgo_u"]
        if riesgo_u <= 0:
            continue
        # Fracciones de accion: sin esto se descartaban los valores caros
        acc = (equity * CONFIG["riesgo_por_op"]) / riesgo_u
        acc = min(acc, (equity * MAX_PESO) / precio)
        coste = acc * precio * (1 + COM)
        if acc <= 0 or coste > cart["cash"]:
            continue
        cart["cash"] -= coste
        cart["posiciones"][tk] = {
            "fecha": fecha, "precio": round(precio, 2),
            "precio_actual": round(precio, 2), "acciones": round(acc, 4),
            "stop": round(s["_precio"] - riesgo_u, 2), "pnl_pct": 0.0, "dias": 0,
        }

    equity = equity_de(cart, precios_hoy)
    registrar(cart, equity, fecha)
    return equity


# ---------------------------------------------------------------------------
#  CARTERA B: momentum
# ---------------------------------------------------------------------------

def ranking_momentum(cierres, volumenes, fecha, cfg):
    p = cierres
    mom = (p.shift(cfg["gap"]) / p.shift(cfg["gap"] + cfg["lookback"]) - 1).loc[fecha]
    sma = p.rolling(cfg["sma_tendencia"]).mean().loc[fecha]
    vold = (p * volumenes).rolling(20).mean().loc[fecha]
    px = p.loc[fecha]

    ok = ((px > sma) & (px > cfg["precio_minimo"])
          & (vold > cfg["volumen_dolar_min"]) & mom.notna())
    if cfg["momentum_absoluto"]:
        ok = ok & (mom > 0)
    return mom[ok].dropna().sort_values(ascending=False)


def gestionar_momentum(cart, cierres, volumenes, fecha, precios_hoy,
                       regimen_ok, cfg, forzar=False):
    ultimo = cart.get("ultimo_rebalanceo")
    dias = 999 if ultimo is None else (
        pd.Timestamp(fecha) - pd.Timestamp(ultimo)).days
    toca = forzar or dias >= 30   # ~21 sesiones

    equity = equity_de(cart, precios_hoy)
    if not toca:
        registrar(cart, equity, fecha)
        return equity, False, []

    ranking = ranking_momentum(cierres, volumenes, pd.Timestamp(fecha), cfg)

    if not regimen_ok or len(ranking) == 0:
        objetivo = []
    else:
        limite = int(cfg["n_cartera"] * cfg["colchon"])
        conservados = [t for t in cart["posiciones"] if t in ranking.index[:limite]]
        huecos = cfg["n_cartera"] - len(conservados)
        nuevos = [t for t in ranking.index if t not in conservados][:max(huecos, 0)]
        objetivo = conservados + nuevos

    # --- Vender lo que ha perdido el liderazgo ---
    for tk in list(cart["posiciones"]):
        if tk in objetivo:
            continue
        px = precios_hoy.get(tk)
        if px is None or pd.isna(px):
            continue
        cerrar(cart, tk, float(px) * (1 - SLIP), fecha, "rotacion")

    # --- Ajustar a pesos iguales ---
    equity = equity_de(cart, precios_hoy)
    if objetivo:
        peso = 1 / len(objetivo)
        for tk in objetivo:
            px = precios_hoy.get(tk)
            if px is None or pd.isna(px) or float(px) <= 0:
                continue
            px = float(px)
            actual = cart["posiciones"].get(tk, {}).get("acciones", 0.0)
            delta = (equity * peso) / px - actual

            if delta > 0:
                pc = px * (1 + SLIP)
                coste = delta * pc * (1 + COM)
                if coste > cart["cash"]:
                    delta = max((cart["cash"] / (pc * (1 + COM))) * 0.99, 0)
                    coste = delta * pc * (1 + COM)
                if delta <= 0:
                    continue
                cart["cash"] -= coste
                if tk in cart["posiciones"]:
                    p = cart["posiciones"][tk]
                    total = p["acciones"] + delta
                    p["precio"] = round((p["precio"] * p["acciones"] + pc * delta) / total, 2)
                    p["acciones"] = round(total, 4)
                else:
                    cart["posiciones"][tk] = {
                        "fecha": fecha, "precio": round(pc, 2),
                        "precio_actual": round(pc, 2), "acciones": round(delta, 4),
                        "stop": 0, "pnl_pct": 0.0, "dias": 0,
                    }
            elif delta < 0 and tk in cart["posiciones"]:
                pv = px * (1 - SLIP)
                bruto = -delta * pv
                cart["cash"] += bruto - bruto * COM
                cart["posiciones"][tk]["acciones"] = round(actual + delta, 4)

    cart["ultimo_rebalanceo"] = fecha
    equity = equity_de(cart, precios_hoy)
    registrar(cart, equity, fecha)
    top = list(ranking.index[:cfg["n_cartera"]]) if len(ranking) else []
    return equity, True, top


# ---------------------------------------------------------------------------
#  Principal
# ---------------------------------------------------------------------------

def main():
    ahora = datetime.now(timezone.utc)
    print(f"[{ahora:%Y-%m-%d %H:%M}] Ejecucion diaria - dos carteras")

    universo = obtener_universo()
    crudos = descargar(universo, INICIO, None)
    print(f"  {len(crudos)} valores con historico")
    bench = descargar(["SPY"], INICIO, None)["SPY"]

    spy = float(bench["Close"].iloc[-1])
    sma200 = float(bench["Close"].rolling(200).mean().iloc[-1])
    regimen_ok = spy > sma200
    print(f"  SPY {spy:.2f} / SMA200 {sma200:.2f} -> "
          f"{'ALCISTA' if regimen_ok else 'BAJISTA'}")

    fecha = str(bench.index[-1].date())
    datos = {t: preparar_indicadores(d, CONFIG) for t, d in crudos.items()}
    cierres, volumenes = construir_paneles(crudos)
    precios_hoy = cierres.iloc[-1]

    # --- Senyales de pullback ---
    senales = []
    if regimen_ok:
        for tk, d in datos.items():
            f = d.iloc[-1]
            if bool(f["senal_entrada"]) and not pd.isna(f["roc"]):
                ru = CONFIG["atr_multiplo_stop"] * float(f["atr"])
                senales.append({
                    "ticker": tk, "_precio": float(f["Close"]), "_riesgo_u": ru,
                    "precio_ref": round(float(f["Close"]), 2),
                    "stop": round(float(f["Close"]) - ru, 2),
                    "rsi": round(float(f["rsi"]), 1),
                    "atr": round(float(f["atr"]), 2),
                    "roc": round(float(f["roc"]), 1),
                })
        senales.sort(key=lambda x: x["roc"], reverse=True)
    print(f"  Senyales pullback: {len(senales)}")

    carteras = cargar()

    eq_pb = gestionar_pullback(carteras["pullback"], datos, senales, fecha, precios_hoy)
    print(f"  Cartera pullback: {eq_pb:,.2f}")

    primera = carteras["momentum"]["ultimo_rebalanceo"] is None
    eq_mm, rebal, top = gestionar_momentum(
        carteras["momentum"], cierres, volumenes, fecha, precios_hoy,
        regimen_ok, BASE_MOM, forzar=primera)
    print(f"  Cartera momentum: {eq_mm:,.2f}"
          f"{'  (rebalanceada hoy)' if rebal else ''}")

    guardar(carteras)

    # --- Tamanyos sugeridos ---
    for s in senales:
        acc = (eq_pb * CONFIG["riesgo_por_op"]) / s["_riesgo_u"]
        acc = min(acc, (eq_pb * MAX_PESO) / s["_precio"])
        s["acciones"] = round(max(acc, 0), 2)
        s["importe"] = round(s["acciones"] * s["_precio"], 2)
        s["riesgo_eur"] = round(s["acciones"] * s["_riesgo_u"], 2)
        s.pop("_precio")
        s.pop("_riesgo_u")

    def exportar(cart, equity):
        return {
            "equity": round(equity, 2),
            "cash": round(cart["cash"], 2),
            "capital_inicial": cart["capital_inicial"],
            "retorno_pct": round((equity / cart["capital_inicial"] - 1) * 100, 2),
            "posiciones": [{"ticker": t, **p} for t, p in cart["posiciones"].items()],
            "cerradas": cart["cerradas"][-20:][::-1],
            "curva": cart["historico_equity"],
            "ultimo_rebalanceo": cart.get("ultimo_rebalanceo"),
        }

    salida = {
        "generado": ahora.isoformat(),
        "fecha_datos": fecha,
        "es_demo": False,
        "regimen": {"alcista": bool(regimen_ok), "spy": round(spy, 2),
                    "sma200": round(sma200, 2),
                    "distancia_pct": round((spy / sma200 - 1) * 100, 2)},
        "senales": senales[:10],
        "cartera": exportar(carteras["pullback"], eq_pb),
        "cartera_momentum": exportar(carteras["momentum"], eq_mm),
        "top_momentum": top[:10],
        "universo": len(crudos),
        "metricas": {},
        "buy_and_hold_spy": 0,
        "curva_backtest": [],
    }

    # Conserva las metricas del backtest historico si ya existian
    if os.path.exists(RUTA_RESULTADOS):
        try:
            with open(RUTA_RESULTADOS, encoding="utf-8") as f:
                previo = json.load(f)
            for k in ("metricas", "buy_and_hold_spy", "curva_backtest"):
                if previo.get(k):
                    salida[k] = previo[k]
        except Exception:
            pass

    with open(RUTA_RESULTADOS, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)
    print("  results.json actualizado")


if __name__ == "__main__":
    main()
