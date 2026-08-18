"""
=============================================================================
 MOTOR v2  --  corrige los fallos detectados en el diagnostico de v1
=============================================================================

 QUE CAMBIA RESPECTO A v1
 ------------------------
 1. FRACCIONES DE ACCION
    v1 usaba int() al calcular el tamanyo. Con 5.000 EUR de capital, en
    valores caros (COST a 900$) salian 0 acciones y la operacion se
    descartaba. El sistema operaba solo los valores baratos del indice,
    que no es lo que dicen las reglas. Ahora el tamanyo es decimal.

 2. SALIDAS CONFIGURABLES
    v1 vendia si RSI>65 O cierre>SMA10. La segunda condicion se cumple
    casi siempre al 2º dia, cortando las ganadoras antes de tiempo:
    ganancia media 17 EUR frente a perdida media 29 EUR. Ahora cada
    mecanismo de salida se activa por separado y se puede medir.

 3. VENTANA TEMPORAL
    Permite acotar el backtest a un rango de fechas, para separar el
    periodo de disenyo del periodo de validacion. Sin esta separacion
    cualquier resultado es sospechoso de sobreajuste.
=============================================================================
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
#  Configuracion base. El barrido de lab.py sobrescribe claves concretas.
# ---------------------------------------------------------------------------

BASE = {
    # Capital y riesgo
    "capital_inicial":      5000.0,
    "riesgo_por_op":        0.01,
    "max_posiciones":       5,
    "max_peso_posicion":    0.25,
    "fraccionable":         True,     # <-- corrige el sesgo de v1

    # Entrada
    "sma_larga":            200,
    "sma_media":            50,
    "rsi_periodo":          4,
    "rsi_entrada":          25,
    "roc_ranking":          126,

    # Salida: cada mecanismo se activa o desactiva de forma independiente
    "atr_periodo":          14,
    "atr_multiplo_stop":    2.5,
    "usar_rsi_salida":      True,     # vender si RSI supera el umbral
    "rsi_salida":           70,
    "sma_salida":           None,     # None = desactivado; 10 o 20 = periodo
    "trailing_atr":         None,     # None = desactivado; p.ej. 2.0
    "objetivo_R":           None,     # None = desactivado; p.ej. 2.0 (2x riesgo)
    "max_dias_posicion":    15,

    # Liquidez
    "precio_minimo":        10.0,
    "volumen_dolar_min":    10_000_000,

    # Costes por lado
    "comision_pct":         0.0010,
    "slippage_pct":         0.0005,
}


# ---------------------------------------------------------------------------
#  Indicadores
# ---------------------------------------------------------------------------

def rsi(serie, periodo):
    delta = serie.diff()
    g = delta.clip(lower=0).ewm(alpha=1 / periodo, adjust=False).mean()
    p = (-delta.clip(upper=0)).ewm(alpha=1 / periodo, adjust=False).mean()
    return (100 - 100 / (1 + g / p.replace(0, np.nan))).fillna(50)


def atr(df, periodo):
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / periodo, adjust=False).mean()


def indicadores(df, cfg):
    d = df.copy()
    d["sma_larga"] = d["Close"].rolling(cfg["sma_larga"]).mean()
    d["sma_media"] = d["Close"].rolling(cfg["sma_media"]).mean()
    d["rsi"] = rsi(d["Close"], cfg["rsi_periodo"])
    d["atr"] = atr(d, cfg["atr_periodo"])
    d["roc"] = d["Close"].pct_change(cfg["roc_ranking"]) * 100
    d["vol_dolar"] = (d["Close"] * d["Volume"]).rolling(20).mean()

    d["senal_entrada"] = (
        (d["Close"] > d["sma_larga"])
        & (d["sma_media"] > d["sma_larga"])
        & (d["rsi"] < cfg["rsi_entrada"])
        & (d["Close"] > cfg["precio_minimo"])
        & (d["vol_dolar"] > cfg["volumen_dolar_min"])
        & (d["atr"] > 0)
    )

    # --- Salida por sobrecompra y/o por media movil ---
    salida = pd.Series(False, index=d.index)
    if cfg["usar_rsi_salida"]:
        salida = salida | (d["rsi"] > cfg["rsi_salida"])
    if cfg["sma_salida"]:
        d["sma_sal"] = d["Close"].rolling(cfg["sma_salida"]).mean()
        salida = salida | (d["Close"] > d["sma_sal"])
    d["senal_salida"] = salida
    return d


# ---------------------------------------------------------------------------
#  Motor
# ---------------------------------------------------------------------------

class Motor:
    def __init__(self, datos, benchmark, cfg):
        self.cfg = cfg
        self.datos = {t: indicadores(d, cfg) for t, d in datos.items()}
        b = benchmark.copy()
        b["regimen_ok"] = b["Close"] > b["Close"].rolling(200).mean()
        self.benchmark = b
        self.cash = cfg["capital_inicial"]
        self.pos = {}
        self.ops = []
        self.curva = []

    def ejecutar(self, calendario):
        cfg = self.cfg
        com, slip = cfg["comision_pct"], cfg["slippage_pct"]

        for i in range(1, len(calendario)):
            hoy, ayer = calendario[i], calendario[i - 1]

            # ---------- SALIDAS ----------
            for tk in list(self.pos):
                p = self.pos[tk]
                d = self.datos[tk]
                if hoy not in d.index:
                    continue
                barra = d.loc[hoy]

                # El trailing eleva el stop segun avanza el precio a favor
                if cfg["trailing_atr"]:
                    p["max"] = max(p["max"], float(barra["High"]))
                    nuevo = p["max"] - cfg["trailing_atr"] * p["atr_ent"]
                    p["stop"] = max(p["stop"], nuevo)

                precio, motivo = None, None
                if barra["Open"] <= p["stop"]:
                    precio, motivo = float(barra["Open"]), "stop_gap"
                elif barra["Low"] <= p["stop"]:
                    precio, motivo = p["stop"], "stop"
                elif cfg["objetivo_R"] and barra["High"] >= p["objetivo"]:
                    precio, motivo = p["objetivo"], "objetivo_R"
                elif ayer in d.index and bool(d.loc[ayer, "senal_salida"]):
                    precio, motivo = float(barra["Open"]), "senal"
                elif p["dias"] >= cfg["max_dias_posicion"]:
                    precio, motivo = float(barra["Open"]), "tiempo"

                if precio is not None:
                    pv = precio * (1 - slip)
                    bruto = pv * p["acc"]
                    self.cash += bruto - bruto * com
                    self.ops.append({
                        "ticker": tk, "entrada": p["precio"], "salida": pv,
                        "pnl": (pv - p["precio"]) * p["acc"],
                        "pnl_pct": (pv / p["precio"] - 1) * 100,
                        "dias": p["dias"], "motivo": motivo,
                        "riesgo": p["riesgo_u"] * p["acc"],
                        "fecha": hoy,
                    })
                    del self.pos[tk]
                else:
                    p["dias"] += 1

            # ---------- VALORACION ----------
            equity = self.cash
            for tk, p in self.pos.items():
                d = self.datos[tk]
                c = float(d.loc[hoy, "Close"]) if hoy in d.index else p["precio"]
                equity += c * p["acc"]
            self.curva.append({"fecha": hoy, "equity": equity})

            # ---------- REGIMEN ----------
            if ayer not in self.benchmark.index:
                continue
            if not bool(self.benchmark.loc[ayer, "regimen_ok"]):
                continue

            huecos = cfg["max_posiciones"] - len(self.pos)
            if huecos <= 0:
                continue

            # ---------- ENTRADAS ----------
            cands = []
            for tk, d in self.datos.items():
                if tk in self.pos or ayer not in d.index or hoy not in d.index:
                    continue
                f = d.loc[ayer]
                if bool(f["senal_entrada"]) and not pd.isna(f["roc"]):
                    cands.append((tk, float(f["roc"]), float(f["atr"])))
            cands.sort(key=lambda x: x[1], reverse=True)

            for tk, _, atr_v in cands[:huecos]:
                barra = self.datos[tk].loc[hoy]
                precio = float(barra["Open"]) * (1 + slip)
                riesgo_u = cfg["atr_multiplo_stop"] * atr_v
                if riesgo_u <= 0 or precio <= 0:
                    continue

                acc = (equity * cfg["riesgo_por_op"]) / riesgo_u
                acc = min(acc, (equity * cfg["max_peso_posicion"]) / precio)
                if not cfg["fraccionable"]:
                    acc = float(int(acc))
                coste = acc * precio
                coste += coste * com
                if acc <= 0 or coste > self.cash:
                    continue

                self.cash -= coste
                self.pos[tk] = {
                    "precio": precio, "acc": acc,
                    "stop": float(barra["Open"]) - riesgo_u,
                    "objetivo": precio + (cfg["objetivo_R"] or 0) * riesgo_u,
                    "riesgo_u": riesgo_u, "atr_ent": atr_v,
                    "max": float(barra["High"]), "dias": 0,
                }
        return self.metricas()

    # -----------------------------------------------------------------
    def metricas(self):
        curva = pd.DataFrame(self.curva).set_index("fecha")["equity"]
        ops = pd.DataFrame(self.ops)
        cap = self.cfg["capital_inicial"]

        if len(ops) < 5 or len(curva) < 10:
            return {"ops": len(ops), "cagr": 0, "dd": 0, "pf": 0,
                    "win": 0, "R": 0, "sharpe": 0, "final": cap, "dias": 0}, curva, ops

        anyos = max((curva.index[-1] - curva.index[0]).days / 365.25, 0.01)
        gan = ops[ops["pnl"] > 0]["pnl"].sum()
        per = abs(ops[ops["pnl"] <= 0]["pnl"].sum())
        rets = curva.pct_change().dropna()

        return {
            "ops": len(ops),
            "final": float(curva.iloc[-1]),
            "cagr": (curva.iloc[-1] / cap) ** (1 / anyos) - 1,
            "dd": float((curva / curva.cummax() - 1).min()),
            "pf": gan / per if per > 0 else 99.0,
            "win": (ops["pnl"] > 0).mean(),
            "R": float((ops["pnl"] / ops["riesgo"].replace(0, np.nan)).mean()),
            "sharpe": float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0,
            "dias": float(ops["dias"].mean()),
        }, curva, ops


# ---------------------------------------------------------------------------
#  Utilidad: recortar el historico a una ventana temporal
# ---------------------------------------------------------------------------

def recortar(datos, inicio, fin):
    """Devuelve solo el tramo pedido, dejando margen previo para que
    los indicadores de 200 sesiones esten ya calculados al empezar."""
    margen = pd.Timestamp(inicio) - pd.Timedelta(days=400)
    out = {}
    for t, d in datos.items():
        trozo = d.loc[(d.index >= margen) & (d.index <= pd.Timestamp(fin))]
        if len(trozo) > 250:
            out[t] = trozo
    return out
