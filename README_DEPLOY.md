# Pozolería - Despliegue en GitHub y Render

## 1. Preparar repositorio Git
```bash
git init
git add .
git commit -m "Inicial: proyecto pozoleria"
# Crear repo remoto primero en GitHub (ej: pozoleria)
git remote add origin https://github.com/<TU_USUARIO>/pozoleria.git
git push -u origin main
```
Si tu rama principal es master:
```bash
git branch -M main
```

## 2. Variables de entorno (.env)
Copia `.env.example` a `.env` y completa:
```
FLASK_SECRET_KEY=valor_seguro
DATABASE_URL=postgresql://usuario:pass@host:5432/dbname  # (Render te la dará si usas PostgreSQL)
TELEGRAM_TOKEN=token_bot
TELEGRAM_ADMIN_CHAT_ID=123456789
TELEGRAM_USE_POLLING=0  # En producción webhooks o nada
FLASK_DEBUG=0
```

No subas `.env` al repositorio (está ignorado).

## 3. Base de datos
- Local: usa SQLite (archivo `pozoleria_new.db` en `instance/`).
- Producción: crea un servicio PostgreSQL en Render y copia la URL a `DATABASE_URL`.
  Render da una URL tipo:
  `postgres://user:pass@host:5432/db`
  El código ya la normaliza a `postgresql://` si hace falta.

## 4. Despliegue en Render
1. En Render: New + Web Service.
2. Conecta tu repositorio de GitHub.
3. Selecciona root del repo.
4. Elige Python.
5. Build Command: `pip install -r requirements.txt`
6. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers=3 --timeout 120`
7. Añade variables de entorno (Environment) con los valores seguros.
8. Deploy.

## 5. Webhook de Telegram (opcional)
Una vez desplegado y obtenida la URL pública (ej: https://pozoleria.onrender.com):
```
GET https://pozoleria.onrender.com/telegram/set_webhook?url=https://pozoleria.onrender.com
```
Para eliminar:
```
GET https://pozoleria.onrender.com/telegram/delete_webhook
```
En producción pon `TELEGRAM_USE_POLLING=0`.

## 6. Carpetas importantes
- `app.py` app Flask.
- `models.py` modelos SQLAlchemy.
- `static/uploads/` imágenes (carpeta vacía trackeada con `.gitkeep`).

## 7. Migraciones ligeras
`ensure_schema()` en `app.py` añade columnas faltantes simples. Para cambios mayores considera integrar Alembic.

## 8. SSE (estado de pedidos)
Endpoint: `/sse/pedido/<NUMERO>` mantiene actualizaciones en tiempo real del estado del pedido.

## 9. Desarrollo local
```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # edita los valores
python app.py
```
Visita: http://localhost:5000

## 10. Seguridad / Buenas prácticas
- Cambia la `SECRET_KEY`.
- No expongas el token de Telegram.
- Revisa logs en Render para errores de tiempo de ejecución.

---
Listo para desplegar.
