"use client";

import { useState } from "react";
import datos from "../public/data/results.json";
import type { Resultados, Cartera, Senal, ParametrosPullback } from "../lib/tipos";

const r = datos as unknown as Resultados;

/* ------------------------------------------------------------------ */
/*  Utilidades de formato                                              */
/* ------------------------------------------------------------------ */

const eur = (n: number) =>
  n.toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const acc = (n: number) =>
  n.toLocaleString("es-ES", { maximumFractionDigits: 2 });

const signo = (n: number) => (n >= 0 ? "+" : "");
const clase = (n: number) => (n >= 0 ? "positivo" : "negativo");

const fecha = (s: string) =>
  new Date(s).toLocaleDateString("es-ES", { day: "2-digit", month: "short" });

const fechaLarga = (s: string) =>
  new Date(s).toLocaleDateString("es-ES", {
    day: "2-digit", month: "short", year: "2-digit" });

const diasDesde = (s: string) =>
  Math.max(0, Math.round((Date.now() - new Date(s).getTime()) / 86400000));

/* ------------------------------------------------------------------ */
/*  Curva de equity dibujada como SVG, sin librerías                   */
/* ------------------------------------------------------------------ */

function Curva({ puntos, color }: { puntos: { d: string; v: number }[]; color: string }) {
  if (puntos.length < 2) {
    return <p className="nota">Se dibujará cuando haya al menos dos días de historial.</p>;
  }
  const W = 800, H = 200, P = 8;
  const vals = puntos.map((p) => p.v);
  const min = Math.min(...vals), max = Math.max(...vals);
  const rango = max - min || 1;
  const x = (i: number) => (i / (puntos.length - 1)) * (W - P * 2) + P;
  const y = (v: number) => H - P - ((v - min) / rango) * (H - P * 2);
  const linea = puntos.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
  const area = `${linea} L${x(puntos.length - 1).toFixed(1)},${H} L${x(0).toFixed(1)},${H} Z`;

  return (
    <div className="grafico">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
           aria-label={`Evolución del capital de ${eur(min)} a ${eur(max)}`}>
        <defs>
          <linearGradient id="relleno" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#relleno)" />
        <path d={linea} fill="none" stroke={color} strokeWidth="1.75"
              strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className="orden-fila" style={{ marginTop: 10 }}>
        <span className="dato nota">{fecha(puntos[0].d)} · {eur(puntos[0].v)}</span>
        <span className="dato nota">{fecha(puntos[puntos.length - 1].d)} · {eur(puntos[puntos.length - 1].v)}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Explicación de una señal: por qué esta y por qué esa cantidad      */
/* ------------------------------------------------------------------ */

function ExplicacionSenal({ s, params }: { s: Senal; params?: ParametrosPullback }) {
  const f = s.fundamental;
  const tieneFund = f && (f.sector || f.per || f.cap_b);

  return (
    <details className="explicacion-detalle">
      <summary className="info-toggle" aria-label={`Por qué ${s.ticker}`}>i</summary>
      <div className="explicacion">
        <div className="explicacion-grupo">
          <div className="explicacion-titulo">Por qué aparece</div>
          <div className="criterio">
            <span className="criterio-check">✓</span>
            <span className="criterio-texto">
              Tendencia alcista: precio <b>{eur(s.precio_ref)}</b> por encima de su
              media de 200 sesiones (<b>{s.sma200 ? eur(s.sma200) : "—"}</b>), y la
              media de 50 (<b>{s.sma50 ? eur(s.sma50) : "—"}</b>) por encima de la de 200.
            </span>
          </div>
          <div className="criterio">
            <span className="criterio-check">✓</span>
            <span className="criterio-texto">
              Retroceso de corto plazo: RSI(4) en <b>{s.rsi}</b>, por debajo del
              umbral de {params?.rsi_entrada ?? 25}.
            </span>
          </div>
          <div className="criterio">
            <span className="criterio-check">✓</span>
            <span className="criterio-texto">
              Liquidez suficiente: volumen medio de{" "}
              <b>{s.vol_dolar_m ? `${s.vol_dolar_m}M $` : "—"}</b> al día.
            </span>
          </div>
          <div className="criterio">
            <span className="criterio-check">✓</span>
            <span className="criterio-texto">
              Fuerza relativa: <b>{signo(s.roc)}{s.roc}%</b> a 6 meses — puesto{" "}
              <b>{s.ranking ?? "?"}</b> de <b>{s.num_candidatos ?? "?"}</b> valores
              que cumplían el resto de condiciones hoy.
            </span>
          </div>
        </div>

        <div className="explicacion-grupo">
          <div className="explicacion-titulo">Por qué esa cantidad</div>
          <div className="formula">
{`Riesgo asumido = ${((params?.riesgo_por_op ?? 0.01) * 100).toFixed(0)}% del capital
Stop = precio − (${params?.atr_multiplo_stop ?? 2.5} × ATR) = ${eur(s.precio_ref)} − (${params?.atr_multiplo_stop ?? 2.5} × ${eur(s.atr)}) = `}<span className="resultado">{eur(s.stop)}</span>{`
Distancia al stop = `}<span className="resultado">{eur(s.atr * (params?.atr_multiplo_stop ?? 2.5))}</span>{` por acción

Acciones = (riesgo en € ÷ distancia al stop), topado al ${((params?.max_peso_posicion ?? 0.25) * 100).toFixed(0)}% de la cartera
        → `}<span className="resultado">{acc(s.acciones)} acciones · {eur(s.importe)} $ · riesgo {eur(s.riesgo_eur)} $</span>
          </div>
        </div>

        {tieneFund && (
          <div className="explicacion-grupo" style={{ marginBottom: 0 }}>
            <div className="explicacion-titulo">
              Contexto fundamental <span style={{ opacity: 0.7 }}>(no filtra, solo informativo)</span>
            </div>
            <div>
              {f?.sector && <span className="fundamental-chip">Sector <b>{f.sector}</b></span>}
              {f?.per && <span className="fundamental-chip">PER <b>{f.per}</b></span>}
              {f?.cap_b && <span className="fundamental-chip">Cap. <b>{f.cap_b} mM$</b></span>}
              {f?.margen_pct != null && <span className="fundamental-chip">Margen <b>{f.margen_pct}%</b></span>}
            </div>
          </div>
        )}
      </div>
    </details>
  );
}

/* ------------------------------------------------------------------ */
/*  Bloque de cartera, reutilizable para las dos estrategias           */
/* ------------------------------------------------------------------ */

function BloqueCartera({ c, nota }: { c: Cartera; nota: string }) {
  return (
    <div className="panel panel--activo">
      <div className={`panel-cifra ${clase(c.retorno_pct)}`}>
        {signo(c.retorno_pct)}{c.retorno_pct}%
      </div>
      <p className="nota">
        {eur(c.equity)} · liquidez {eur(c.cash)} · {c.posiciones.length} abiertas
      </p>
      <p className="nota" style={{ marginTop: 6 }}>{nota}</p>

      {c.posiciones.length > 0 && (
        <div className="desplazable" style={{ marginTop: 20 }}>
          <table className="tabla">
            <thead>
              <tr>
                <th>Valor</th><th>Entrada</th><th>Acc.</th>
                <th>Compra</th><th>Actual</th><th>Total</th>
                <th>Stop</th><th>Result.</th>
              </tr>
            </thead>
            <tbody>
              {c.posiciones.map((p) => {
                const total = p.precio_actual * p.acciones;
                const invertido = p.precio * p.acciones;
                return (
                  <tr key={p.ticker}>
                    <td style={{ fontWeight: 600 }}>{p.ticker}</td>
                    <td className="fecha-entrada">
                      {fechaLarga(p.fecha)}
                      <span style={{ opacity: 0.6 }}> · {diasDesde(p.fecha)}d</span>
                    </td>
                    <td>{acc(p.acciones)}</td>
                    <td>{eur(p.precio)}</td>
                    <td>{eur(p.precio_actual)}</td>
                    <td style={{ fontWeight: 600 }}>{eur(total)}</td>
                    <td className={p.stop > 0 ? "negativo" : ""}>
                      {p.stop > 0 ? eur(p.stop) : "—"}
                    </td>
                    <td className={clase(p.pnl_pct)}>
                      {signo(p.pnl_pct)}{p.pnl_pct}%
                      <span style={{ opacity: 0.65, fontSize: "0.85em" }}>
                        {" "}({signo(total - invertido)}{eur(total - invertido)})
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="fila-total">
                <td colSpan={5}>Invertido</td>
                <td style={{ fontWeight: 600 }}>
                  {eur(c.posiciones.reduce((a, p) => a + p.precio_actual * p.acciones, 0))}
                </td>
                <td colSpan={2} style={{ color: "var(--apagado)" }}>
                  + {eur(c.cash)} en liquidez
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {c.curva.length >= 2 && (
        <div style={{ marginTop: 20 }}>
          <Curva puntos={c.curva} color={c.retorno_pct >= 0 ? "#5fd3a6" : "#e8705f"} />
        </div>
      )}

      {c.cerradas.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <span className="epigrafe">Cerradas recientemente</span>
          <div className="desplazable" style={{ marginTop: 10 }}>
            <table className="tabla">
              <thead>
                <tr>
                  <th>Valor</th><th>Entrada</th><th>Salida</th><th>Acc.</th>
                  <th>Compra</th><th>Venta</th><th>Result.</th>
                  <th>Días</th><th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {c.cerradas.slice(0, 10).map((x, i) => (
                  <tr key={`${x.ticker}-${i}`}>
                    <td style={{ fontWeight: 600 }}>{x.ticker}</td>
                    <td className="fecha-entrada">{fechaLarga(x.entrada_fecha)}</td>
                    <td className="fecha-entrada">{fechaLarga(x.salida_fecha)}</td>
                    <td>{acc(x.acciones ?? 0)}</td>
                    <td>{eur(x.entrada)}</td>
                    <td>{eur(x.salida)}</td>
                    <td className={clase(x.pnl_pct)}>
                      {signo(x.pnl_pct)}{x.pnl_pct}%
                      <span style={{ opacity: 0.65, fontSize: "0.85em" }}>
                        {" "}({signo(x.pnl)}{eur(x.pnl)})
                      </span>
                    </td>
                    <td>{x.dias}</td>
                    <td style={{ color: "var(--apagado)" }}>{x.motivo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Menú lateral                                                       */
/*                                                                      */
/*  Añadir una estrategia nueva el día de mañana = añadir una entrada  */
/*  aquí (id, etiqueta y retorno para el badge) y una rama en el       */
/*  switch de renderVista(). Nada más cambia.                          */
/* ------------------------------------------------------------------ */

type VistaId = "resumen" | "pullback" | "momentum" | "sistema";

function Pagina() {
  const [vista, setVista] = useState<VistaId>("resumen");
  const { regimen, senales, cartera, metricas } = r;
  const momentum = r.cartera_momentum;

  const items: { id: VistaId; etiqueta: string; retorno?: number }[] = [
    { id: "resumen", etiqueta: "Resumen" },
    { id: "pullback", etiqueta: "Pullback", retorno: cartera.retorno_pct },
    ...(momentum ? [{ id: "momentum" as VistaId, etiqueta: "Momentum", retorno: momentum.retorno_pct }] : []),
    { id: "sistema", etiqueta: "Sistema" },
  ];

  return (
    <main className="envoltura">
      <header className="cabecera">
        <div className="marca">
          <h1 className="titulo">Señales swing</h1>
          <span className="epigrafe">{r.universo} valores · S&amp;P 500 + Nasdaq 100</span>
        </div>

        <div className="estado">
          <span className={`punto ${regimen.alcista ? "punto--activo" : "punto--parado"}`} />
          <span>
            {regimen.alcista
              ? "Mercado alcista — el sistema puede abrir posiciones"
              : "Mercado bajista — el sistema no abre posiciones nuevas"}
          </span>
        </div>

        <p className="nota" style={{ marginTop: 12 }}>
          SPY en <span className="dato">{eur(regimen.spy)}</span>, su media de 200 sesiones en{" "}
          <span className="dato">{eur(regimen.sma200)}</span>{" "}
          (<span className={`dato ${clase(regimen.distancia_pct)}`}>
            {signo(regimen.distancia_pct)}{regimen.distancia_pct}%
          </span>). Datos del {r.fecha_datos}.
        </p>

        {r.es_demo && (
          <div className="aviso">
            <strong>Datos de ejemplo.</strong> Lanza el flujo <em>Señales diarias</em> desde
            la pestaña Actions de GitHub para sustituirlos por datos reales de mercado.
          </div>
        )}
      </header>

      <div className="layout">
        {/* ---------- Menú lateral ---------- */}
        <nav className="menu" aria-label="Estrategias">
          {items.map((it) => (
            <button
              key={it.id}
              className={`menu-item ${vista === it.id ? "menu-item--activo" : ""}`}
              onClick={() => setVista(it.id)}
            >
              <span>{it.etiqueta}</span>
              {it.retorno !== undefined && (
                <span className={`menu-badge ${clase(it.retorno)}`}>
                  {signo(it.retorno)}{it.retorno.toFixed(1)}%
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* ---------- Contenido ---------- */}
        <div className="contenido">

          {vista === "resumen" && (
            <>
              <section className="seccion" style={{ marginTop: 0 }}>
                <div className="seccion-cabecera">
                  <span className="epigrafe">Comparativa</span>
                  <h2 className="seccion-titulo">Las dos estrategias, en paralelo</h2>
                  <p className="nota">
                    Mismo capital de partida ({eur(cartera.capital_inicial)}), dinero
                    ficticio, precios reales. Pulsa una pestaña para ver el detalle completo.
                  </p>
                </div>
                <div className="duo">
                  <button className="resumen-card" onClick={() => setVista("pullback")}>
                    <span className="panel-titulo"><span>Pullback</span><span className="etiqueta">diaria</span></span>
                    <div className={`panel-cifra ${clase(cartera.retorno_pct)}`}>
                      {signo(cartera.retorno_pct)}{cartera.retorno_pct}%
                    </div>
                    <p className="nota">{eur(cartera.equity)} · {cartera.posiciones.length} abiertas</p>
                  </button>
                  {momentum && (
                    <button className="resumen-card" onClick={() => setVista("momentum")}>
                      <span className="panel-titulo"><span>Momentum</span><span className="etiqueta">mensual</span></span>
                      <div className={`panel-cifra ${clase(momentum.retorno_pct)}`}>
                        {signo(momentum.retorno_pct)}{momentum.retorno_pct}%
                      </div>
                      <p className="nota">{eur(momentum.equity)} · {momentum.posiciones.length} abiertas</p>
                    </button>
                  )}
                </div>
                {momentum && (
                  <p className="nota" style={{ marginTop: 14 }}>
                    Diferencia:{" "}
                    <span className={`dato ${clase(momentum.retorno_pct - cartera.retorno_pct)}`}>
                      {signo(momentum.retorno_pct - cartera.retorno_pct)}
                      {(momentum.retorno_pct - cartera.retorno_pct).toFixed(2)} puntos
                    </span>{" "}
                    a favor de momentum. Con pocas semanas de historial este número
                    todavía no es informativo.
                  </p>
                )}
              </section>

              <section className="seccion">
                <div className="seccion-cabecera">
                  <span className="epigrafe">Paso 1</span>
                  <h2 className="seccion-titulo">Órdenes para mañana (pullback)</h2>
                  <p className="nota">Cifras listas para copiar en el bróker.</p>
                </div>
                {senales.length === 0 ? (
                  <div className="vacio">
                    <p>Hoy no hay ninguna orden.</p>
                    <p>
                      {regimen.alcista
                        ? "Ningún valor cumple las condiciones de entrada."
                        : "El filtro de régimen está activo: no se abren posiciones."}
                    </p>
                  </div>
                ) : (
                  senales.slice(0, 5).map((s) => (
                    <article className="orden" key={s.ticker}>
                      <div className="orden-fila">
                        <div style={{ display: "flex", alignItems: "baseline" }}>
                          <span className="orden-ticker">{s.ticker}</span>
                          <span className="orden-accion">COMPRAR</span>
                          <ExplicacionSenal s={s} params={r.parametros_pullback} />
                        </div>
                        <span className="orden-importe">{eur(s.importe)} $</span>
                      </div>
                    </article>
                  ))
                )}
                {senales.length > 5 && (
                  <button className="ver-mas" onClick={() => setVista("pullback")}>
                    Ver las {senales.length - 5} señales restantes en la pestaña Pullback →
                  </button>
                )}
              </section>

              {r.top_momentum && r.top_momentum.length > 0 && (
                <section className="seccion">
                  <div className="seccion-cabecera">
                    <span className="epigrafe">Ranking de fuerza actual</span>
                    <p className="nota" style={{ marginTop: 8 }}>
                      Los valores más fuertes hoy. La cartera de momentum se ajustará
                      a esta lista en el próximo rebalanceo, no antes.
                    </p>
                  </div>
                  <p className="dato" style={{ lineHeight: 2 }}>
                    {r.top_momentum.map((t, i) => (
                      <span key={t}>
                        <span style={{ color: "var(--apagado)" }}>{i + 1}.</span> {t}
                        {i < r.top_momentum!.length - 1 ? "   " : ""}
                      </span>
                    ))}
                  </p>
                </section>
              )}
            </>
          )}

          {vista === "pullback" && (
            <section className="seccion" style={{ marginTop: 0 }}>
              <div className="seccion-cabecera">
                <span className="epigrafe">Estrategia diaria</span>
                <h2 className="seccion-titulo">Pullback en tendencia</h2>
                <p className="nota">
                  Compra retrocesos (RSI bajo) en valores sobre su media de 200 sesiones.
                  Posiciones de días. El backtest histórico no le encontró ventaja frente
                  al índice — sigue viva para comprobarlo con precios reales.
                </p>
              </div>

              <div style={{ marginBottom: 28 }}>
                <span className="epigrafe">Órdenes para mañana</span>
                <div style={{ marginTop: 14 }}>
                  {senales.length === 0 ? (
                    <div className="vacio">
                      <p>Hoy no hay ninguna orden.</p>
                      <p>
                        {regimen.alcista
                          ? "Ningún valor cumple las condiciones de entrada."
                          : "El filtro de régimen está activo: no se abren posiciones."}
                      </p>
                    </div>
                  ) : (
                    senales.map((s) => (
                      <article className="orden" key={s.ticker}>
                        <div className="orden-fila">
                          <div style={{ display: "flex", alignItems: "baseline" }}>
                            <span className="orden-ticker">{s.ticker}</span>
                            <span className="orden-accion">COMPRAR</span>
                            <ExplicacionSenal s={s} params={r.parametros_pullback} />
                          </div>
                          <span className="orden-importe">{eur(s.importe)} $</span>
                        </div>
                        <hr className="orden-separador" />
                        <div className="orden-campos">
                          <div><span className="campo-etiqueta">Acciones</span><span className="campo-valor">{acc(s.acciones)}</span></div>
                          <div><span className="campo-etiqueta">Referencia</span><span className="campo-valor">{eur(s.precio_ref)}</span></div>
                          <div><span className="campo-etiqueta">Stop</span><span className="campo-valor negativo">{eur(s.stop)}</span></div>
                          <div><span className="campo-etiqueta">Riesgo</span><span className="campo-valor destacado">{eur(s.riesgo_eur)} $</span></div>
                          <div><span className="campo-etiqueta">RSI(4)</span><span className="campo-valor">{s.rsi}</span></div>
                          <div><span className="campo-etiqueta">Fuerza 6m</span><span className={`campo-valor ${clase(s.roc)}`}>{signo(s.roc)}{s.roc}%</span></div>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </div>

              <span className="epigrafe">Cartera fantasma</span>
              <div style={{ marginTop: 14 }}>
                <BloqueCartera c={cartera} nota="Dinero ficticio, precios reales." />
              </div>
            </section>
          )}

          {vista === "momentum" && momentum && (
            <section className="seccion" style={{ marginTop: 0 }}>
              <div className="seccion-cabecera">
                <span className="epigrafe">Estrategia mensual</span>
                <h2 className="seccion-titulo">Momentum</h2>
                <p className="nota">
                  Mantiene los 10 valores más fuertes por rentabilidad a 12 meses
                  (ignorando el último mes). Rebalanceo cada ~30 días.
                  {momentum.ultimo_rebalanceo && (
                    <> Último rebalanceo: {fechaLarga(momentum.ultimo_rebalanceo)}.</>
                  )}
                </p>
              </div>

              {r.top_momentum && r.top_momentum.length > 0 && (
                <div style={{ marginBottom: 28 }}>
                  <span className="epigrafe">Ranking de fuerza actual</span>
                  <p className="nota" style={{ marginTop: 8 }}>
                    Se aplicará en el próximo rebalanceo, no de inmediato.
                  </p>
                  <p className="dato" style={{ marginTop: 10, lineHeight: 2 }}>
                    {r.top_momentum.map((t, i) => (
                      <span key={t}>
                        <span style={{ color: "var(--apagado)" }}>{i + 1}.</span> {t}
                        {i < r.top_momentum!.length - 1 ? "   " : ""}
                      </span>
                    ))}
                  </p>
                </div>
              )}

              <span className="epigrafe">Cartera fantasma</span>
              <div style={{ marginTop: 14 }}>
                <BloqueCartera c={momentum} nota="Se ajusta solo en cada rebalanceo mensual." />
              </div>
            </section>
          )}

          {vista === "sistema" && (
            <section className="seccion" style={{ marginTop: 0 }}>
              <div className="seccion-cabecera">
                <span className="epigrafe">Validación</span>
                <h2 className="seccion-titulo">Salud del sistema</h2>
                <p className="nota">
                  Resultado de aplicar las reglas de pullback al histórico desde 2015.
                  Si el factor de beneficio baja de 1,3 o la caída máxima supera el 20%,
                  toca revisar las reglas.
                </p>
              </div>

              <div className="rejilla">
                {["CAGR", "Max Drawdown", "Profit factor", "Win rate",
                  "Ratio R medio", "Nº operaciones", "Sharpe", "Días medios"].map((k) => (
                  <div className="celda" key={k}>
                    <span className="campo-etiqueta">{k}</span>
                    <div className="celda-valor">{String(metricas[k] ?? "—")}</div>
                  </div>
                ))}
              </div>

              <p className="nota" style={{ marginTop: 16 }}>
                Comprar y mantener el SPY en el mismo periodo:{" "}
                <span className={`dato ${clase(r.buy_and_hold_spy)}`}>
                  {signo(r.buy_and_hold_spy)}{r.buy_and_hold_spy}%
                </span>. Si el sistema no bate esta cifra ajustada por riesgo, el
                índice es la opción racional.
              </p>

              {r.curva_backtest.length >= 2 && (
                <div style={{ marginTop: 24 }}>
                  <Curva puntos={r.curva_backtest} color="#f2a93b" />
                </div>
              )}
            </section>
          )}
        </div>
      </div>

      <footer className="pie">
        <p>
          Actualizado el {new Date(r.generado).toLocaleString("es-ES")}. El motor se ejecuta
          de lunes a viernes a las 22:30, tras el cierre del mercado americano.
        </p>
        <p style={{ marginTop: 10 }}>
          Herramienta de uso personal. No es asesoramiento financiero. Los resultados históricos
          no anticipan los futuros y operar en bolsa puede acarrear la pérdida del capital.
        </p>
      </footer>
    </main>
  );
}

export default Pagina;
