"""
=============================================================================
 MOTOR MOMENTUM  --  cartera rotatoria de los valores mas fuertes
=============================================================================

 EN QUE SE DIFERENCIA DEL ANTERIOR
 ---------------------------------
 El motor de pullback buscaba senyales cada dia y mantenia posiciones
 4-6 dias: 195 operaciones al anyo, y los costes se comian la ventaja.

 Aqui no hay senyales diarias. Hay una CARTERA que se revisa cada N dias:
 se ordena el universo por fuerza y se mantienen los mejores. Si un valor
 sigue liderando, no se toca. Genera ~40-60 operaciones al anyo en lugar
 de 400, y las ganadoras corren durante meses en vez de dias.

 POR QUE 12 MESES MENOS 1
 ------------------------
 La medida clasica de momentum ignora el ultimo mes. A muy corto plazo
 los precios tienden a revertir, asi que incluirlo mete ruido en contra.
 Se mide de hace 12 meses hasta hace 1 mes.

 EL COLCHON DE ROTACION
 ----------------------
 Si mantienes exactamente el top 10, un valor que caiga al puesto 11
 obliga a vender y recomprar por nada. Con colchon 1.5 se aguanta hasta
 el puesto 15 antes de soltarlo. Menos rotacion, menos costes.
=============================================================================
"""

import numpy as np
import pandas as pd

BASE_MOM = {
    # Capital
    "capital_inicial":      5000.0,

    # Medida de fuerza
    "lookback":             252,      # ~12 meses
    "gap":                  21,       # ignora el ultimo mes
    "momentum_absoluto":    True,     # exige rentabilidad positiva

    # Cartera
    "n_cartera":            10,       # cuantos valores mantener
    "colchon":              1.5,      # se conserva hasta el puesto n*colchon
    "ponderacion":          "igual",  # "igual" o "inv_vol"
    "dias_rebalanceo":      21,       # ~1 mes

    # Salidas intermedias (entre rebalanceos). None = desactivadas.
    "take_profit":          None,     # p.ej. 0.25 -> vender al +25%
    "stop_catastrofe":      None,     # p.ej. -0.25 -> cortar al -25%

    # Filtros
    "usar_regimen":         True,     # fuera del mercado si SPY < SMA200
    "sma_tendencia":        200,      # el valor debe estar sobre su SMA200
    "precio_minimo":        10.0,
    "volumen_dolar_min":    10_000_000,

    # Costes por lado
    "comision_pct":         0.0010,
    "slippage_pct":         0.0005,
}


class MotorMomentum:
    """Rebalanceo periodico. Trabaja con paneles (fechas x tickers)."""

    def __init__(self, cierres, volumenes, benchmark, cfg):
        self.cfg = cfg
        self.precios = cierres
        self.bench = benchmark

        # --- Fuerza relativa: rentabilidad de hace 12 meses a hace 1 mes ---
        p = cierres
        self.momentum = p.shift(cfg["gap"]) / p.shift(cfg["gap"] + cfg["lookback"]) - 1

        # --- Filtros de elegibilidad ---
        sma = p.rolling(cfg["sma_tendencia"]).mean()
        vol_dolar = (p * volumenes).rolling(20).mean()

        elegible = (
            (p > sma)
            & (p > cfg["precio_minimo"])
            & (vol_dolar > cfg["volumen_dolar_min"])
            & self.momentum.notna()
        )
        if cfg["momentum_absoluto"]:
            elegible &= self.momentum > 0
        self.elegible = elegible

        # --- Volatilidad, para la ponderacion inversa ---
        self.volat = p.pct_change().rolling(60).std()

        # --- Regimen de mercado ---
        b = benchmark["Close"]
        self.regimen = b > b.rolling(200).mean()

        self.cash = cfg["capital_inicial"]
        self.cartera = {}        # ticker -> nº de acciones (decimal)
        self.ops = []
        self.curva = []

    # -----------------------------------------------------------------
    def _seleccionar(self, fecha):
        """Devuelve los tickers que deberia contener la cartera hoy."""
        cfg = self.cfg
        if cfg["usar_regimen"] and not bool(self.regimen.loc[fecha]):
            return []

        mom = self.momentum.loc[fecha][self.elegible.loc[fecha]].dropna()
        if len(mom) == 0:
            return []

        ranking = mom.sort_values(ascending=False)
        n = cfg["n_cartera"]
        limite = int(n * cfg["colchon"])

        # Se conservan los que siguen dentro del colchon
        conservados = [t for t in self.cartera if t in ranking.index[:limite]]
        # Y se rellena con los mejores que no estemos ya llevando
        huecos = n - len(conservados)
        nuevos = [t for t in ranking.index if t not in conservados][:max(huecos, 0)]
        return conservados + nuevos

    def _pesos(self, seleccion, fecha):
        cfg = self.cfg
        if not seleccion:
            return {}
        if cfg["ponderacion"] == "inv_vol":
            v = self.volat.loc[fecha, seleccion].replace(0, np.nan)
            inv = (1 / v).fillna(0)
            if inv.sum() > 0:
                return (inv / inv.sum()).to_dict()
        return {t: 1 / len(seleccion) for t in seleccion}

    # -----------------------------------------------------------------
    def ejecutar(self, calendario):
        cfg = self.cfg
        com, slip = cfg["comision_pct"], cfg["slippage_pct"]
        proximo = 0

        if not hasattr(self, "entradas"):
            self.entradas = {}

        for i, fecha in enumerate(calendario):
            precios_hoy = self.precios.loc[fecha]

            # ---- Salidas intermedias, revisadas a diario ----
            # El take profit va en contra de la logica del momentum (corta
            # las ganadoras que sostienen la estrategia). Se deja como
            # opcion para poder MEDIR su efecto en lugar de suponerlo.
            if cfg["take_profit"] or cfg["stop_catastrofe"]:
                for t in list(self.cartera):
                    ent = self.entradas.get(t)
                    px = precios_hoy.get(t)
                    if ent is None or pd.isna(px):
                        continue
                    var = px / ent["precio"] - 1
                    motivo = None
                    if cfg["take_profit"] and var >= cfg["take_profit"]:
                        motivo = "take_profit"
                    elif cfg["stop_catastrofe"] and var <= cfg["stop_catastrofe"]:
                        motivo = "stop_catastrofe"
                    if motivo:
                        pv = px * (1 - slip)
                        bruto = pv * self.cartera[t]
                        self.cash += bruto - bruto * com
                        self.ops.append({
                            "ticker": t, "fecha": fecha, "tipo": "venta",
                            "importe": bruto,
                            "pnl": (pv - ent["precio"]) * self.cartera[t],
                            "dias": (fecha - ent["fecha"]).days,
                            "motivo": motivo,
                        })
                        del self.cartera[t]
                        del self.entradas[t]

            # ---- Valoracion diaria ----
            valor = self.cash
            for t, acc in self.cartera.items():
                px = precios_hoy.get(t)
                if pd.notna(px):
                    valor += px * acc
            self.curva.append({"fecha": fecha, "equity": valor})

            # ---- Rebalanceo ----
            if i < proximo:
                continue
            proximo = i + cfg["dias_rebalanceo"]

            seleccion = self._seleccionar(fecha)
            pesos = self._pesos(seleccion, fecha)

            # 1) Vender lo que sale de la cartera
            for t in list(self.cartera):
                if t not in pesos:
                    px = precios_hoy.get(t)
                    if pd.isna(px):
                        continue
                    pv = px * (1 - slip)
                    bruto = pv * self.cartera[t]
                    self.cash += bruto - bruto * com
                    ent = self.entradas.get(t) if hasattr(self, "entradas") else None
                    self.ops.append({
                        "ticker": t, "fecha": fecha, "tipo": "venta",
                        "importe": bruto,
                        "pnl": (pv - ent["precio"]) * self.cartera[t] if ent else 0.0,
                        "dias": (fecha - ent["fecha"]).days if ent else 0,
                        "motivo": "rotacion",
                    })
                    del self.cartera[t]

            # 2) Ajustar a los pesos objetivo
            objetivo_total = self.cash + sum(
                precios_hoy.get(t, 0) * a for t, a in self.cartera.items()
            )

            for t, w in pesos.items():
                px = precios_hoy.get(t)
                if pd.isna(px) or px <= 0:
                    continue
                objetivo_acc = (objetivo_total * w) / px
                delta = objetivo_acc - self.cartera.get(t, 0.0)

                if delta > 0:
                    pc = px * (1 + slip)
                    coste = delta * pc
                    coste += coste * com
                    if coste > self.cash:
                        delta = max((self.cash / (pc * (1 + com))) * 0.99, 0)
                        coste = delta * pc * (1 + com)
                    if delta <= 0:
                        continue
                    self.cash -= coste
                    self.cartera[t] = self.cartera.get(t, 0.0) + delta
                    if t not in self.entradas:
                        self.entradas[t] = {"precio": pc, "fecha": fecha}
                        self.ops.append({"ticker": t, "fecha": fecha,
                                         "tipo": "compra", "importe": coste,
                                         "pnl": 0.0, "dias": 0})
                elif delta < 0:
                    pv = px * (1 - slip)
                    bruto = -delta * pv
                    self.cash += bruto - bruto * com
                    self.cartera[t] += delta

            for t in list(self.entradas):
                if t not in self.cartera:
                    del self.entradas[t]

        return self.metricas()

    # -----------------------------------------------------------------
    def metricas(self):
        curva = pd.DataFrame(self.curva).set_index("fecha")["equity"]
        ops = pd.DataFrame(self.ops)
        cap = self.cfg["capital_inicial"]

        vacio = {"ops": 0, "cagr": 0.0, "dd": 0.0, "pf": 0.0, "win": 0.0,
                 "sharpe": 0.0, "final": cap, "dias": 0.0, "rot": 0.0}
        if len(curva) < 30 or len(ops) == 0:
            return vacio, curva, ops

        ventas = ops[ops["tipo"] == "venta"] if "tipo" in ops else ops
        compras = ops[ops["tipo"] == "compra"] if "tipo" in ops else ops

        anyos = max((curva.index[-1] - curva.index[0]).days / 365.25, 0.01)
        rets = curva.pct_change().dropna()

        gan = ventas[ventas["pnl"] > 0]["pnl"].sum() if len(ventas) else 0.0
        per = abs(ventas[ventas["pnl"] <= 0]["pnl"].sum()) if len(ventas) else 0.0

        return {
            "ops": int(len(compras)),
            "final": float(curva.iloc[-1]),
            "cagr": float((curva.iloc[-1] / cap) ** (1 / anyos) - 1),
            "dd": float((curva / curva.cummax() - 1).min()),
            "pf": float(gan / per) if per > 0 else 99.0,
            "win": float((ventas["pnl"] > 0).mean()) if len(ventas) else 0.0,
            "sharpe": float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0,
            "dias": float(ventas["dias"].mean()) if len(ventas) else 0.0,
            "rot": float(len(compras) / anyos),
        }, curva, ops


# ---------------------------------------------------------------------------
#  Construccion de paneles a partir del dict de DataFrames
# ---------------------------------------------------------------------------

def construir_paneles(datos):
    cierres = pd.DataFrame({t: d["Close"] for t, d in datos.items()})
    volumenes = pd.DataFrame({t: d["Volume"] for t, d in datos.items()})
    return cierres.sort_index(), volumenes.sort_index()
