# Señales swing — S&P 500 + Nasdaq 100

Sistema de trading swing con señales diarias, cartera fantasma y métricas de backtest.

## Cómo funciona

```
GitHub Actions          →   public/data/*.json   →   Vercel
(calcula, 10 min/día)       (resultados)             (muestra la web)
```

GitHub ejecuta el motor en Python cada día a las 22:30 CET, tras el cierre americano.
Guarda los resultados en el repositorio. Vercel detecta el cambio y actualiza la web sola.

No hay servidores que mantener ni bases de datos que configurar. Todo gratuito.

---

## Puesta en marcha

### 1. Subir a GitHub

Crea un repositorio nuevo en github.com y sube esta carpeta.
Puede ser público o privado; con privado, comprueba que tienes minutos de Actions disponibles.

### 2. Dar permiso de escritura a Actions

En el repositorio: **Settings → Actions → General → Workflow permissions**
→ marca **Read and write permissions** → Save.

Sin este paso el motor calcula pero no puede publicar los resultados.

### 3. Lanzar el primer cálculo

Pestaña **Actions** → *Señales diarias* → **Run workflow**.

Tarda entre 8 y 15 minutos: descarga unos 520 valores con 11 años de histórico
y simula la estrategia completa. A partir de aquí se ejecuta solo cada día laborable.

### 4. Publicar en Vercel

En vercel.com → **Add New → Project** → importa el repositorio.
Next.js se detecta automáticamente, no hay que configurar nada. Deploy.

Cada vez que el motor publique resultados nuevos, Vercel redesplegará la web.

---

## Qué verás

**Órdenes para mañana** — lo que hay que ejecutar en la apertura siguiente:
ticker, número de acciones, precio de referencia, stop y riesgo en euros.

**Cartera fantasma** — dinero ficticio operando con precios reales. Es el termómetro:
si aquí no funciona en 3-6 meses, no funcionará con dinero de verdad.

**Salud del sistema** — resultado del backtest histórico. Los dos números que importan
son el factor de beneficio (mínimo 1,3) y la caída máxima (máximo 20%).

---

## Ajustar la estrategia

Todos los parámetros están en `engine/backtest_v1.py`, en el diccionario `CONFIG`
al principio del archivo, comentados uno por uno. Cambia un valor, haz commit,
y lanza el workflow a mano para ver el efecto.

Un consejo: cambia **un solo parámetro cada vez**. Si tocas cinco y el resultado mejora,
no sabrás cuál fue y probablemente sea casualidad.

---

## Aviso

Herramienta de uso personal. No es asesoramiento financiero.
Los resultados históricos no anticipan los futuros y operar en bolsa
puede acarrear la pérdida del capital invertido.
