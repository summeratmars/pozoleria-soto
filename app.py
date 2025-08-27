from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response
from datetime import datetime
import os, random, string, json
from sqlalchemy import text

# Cargar variables de entorno ANTES de importar módulos que leen os.getenv
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from extensions import db
from admin import admin_bp
from models import (
    Sucursal, MenuItem, PedidoCliente, Extra, Categoria, HorarioSucursal,
    OpcionPersonalizada, ValorOpcion
)
from telegram_bot import enviar_notificacion_pedido, procesar_update, TELEGRAM_TOKEN, poll_once, iniciar_polling_background
from event_bus import sse_stream

# Marca simple de versión del archivo para depuración de recargas
CODE_VERSION = 'timeline-progreso-2025-08-27-1'

app = Flask(__name__)

# Secret key configurable vía entorno
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')

def _database_uri():
    uri = os.getenv('DATABASE_URL', 'sqlite:///pozoleria_new.db')
    # Normalizar URL de postgres (Render suele usar postgres:// )
    if uri.startswith('postgres://'):
        uri = uri.replace('postgres://', 'postgresql://', 1)
    # Añadir sslmode=require si es Postgres remoto y no viene ya
    if uri.startswith('postgresql://') and 'sslmode=' not in uri:
        # Separar query params
        if '?' in uri:
            uri += '&sslmode=require'
        else:
            uri += '?sslmode=require'
    # Forzar uso de nuevo driver psycopg si no se especifica (evitar psycopg2 por defecto en SQLAlchemy)
    if uri.startswith('postgresql://') and '+psycopg' not in uri:
        uri = uri.replace('postgresql://', 'postgresql+psycopg://', 1)
    return uri

app.config['SQLALCHEMY_DATABASE_URI'] = _database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,      # Detecta conexiones muertas antes de usarlas
    'pool_recycle': 300,        # Recicla conexiones cada 5 min para evitar cortes por inactividad
    'pool_size': int(os.getenv('DB_POOL_SIZE', 5)),
    'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', 5)),
}
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Agregar filtro personalizado para convertir JSON
@app.template_filter('fromjson')
def fromjson_filter(json_str):
    """Filtro para convertir string JSON a objeto Python"""
    try:
        return json.loads(json_str) if json_str else []
    except (json.JSONDecodeError, TypeError):
        return []

def generar_numero_pedido():
    """Genera un número de pedido único de 8 caracteres"""
    while True:
        # Generar código: 2 letras + 6 números
        letras = ''.join(random.choices(string.ascii_uppercase, k=2))
        numeros = ''.join(random.choices(string.digits, k=6))
        numero_pedido = letras + numeros
        
        # Verificar que no exista en la base de datos
        if not PedidoCliente.query.filter_by(numero_pedido=numero_pedido).first():
            return numero_pedido

def is_mobile_device():
    """Detecta si el request viene de un dispositivo móvil"""
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_patterns = [
        'mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 
        'windows phone', 'webos', 'nokia', 'opera mini', 'palm'
    ]
    return any(pattern in user_agent for pattern in mobile_patterns)

def get_base_template():
    """Devuelve el template base apropiado según el dispositivo"""
    if is_mobile_device():
        return 'base_mobile.html'
    else:
        return 'base_desktop.html'

db.init_app(app)
app.register_blueprint(admin_bp)

# Auto-migración ligera para evitar errores 'no such column' en entornos sin alembic.
def ensure_schema():
    """Auto-ajustes mínimos SOLO para SQLite; en otros motores solo crea tablas.

    Evita ejecutar PRAGMA / ALTER inseguros en PostgreSQL.
    """
    with app.app_context():
        try:
            engine = db.engine  # evitar deprecation get_engine
            dialect = engine.dialect.name
            if dialect == 'sqlite':
                try:
                    info = db.session.execute(text("PRAGMA table_info(administrador)")).all()
                    columnas = [row[1] for row in info]
                    if 'rol' not in columnas:
                        db.session.execute(text("ALTER TABLE administrador ADD COLUMN rol VARCHAR(20) DEFAULT 'empleado'"))
                        db.session.commit()
                except Exception as inner:
                    print(f"[AUTO-MIGRACION][sqlite] Aviso: {inner}")
            else:
                # Para PostgreSQL (u otros) confiar en models + create_all inicial
                pass
            db.create_all()
        except Exception as e:
            print(f"[AUTO-MIGRACION] Advertencia: {e}")

# Ejecutar verificación al cargar el módulo
ensure_schema()

# Seed opcional de administrador inicial (solo si variables están definidas y no existe)
def ensure_seed_admin():
    try:
        from models import Administrador
        user = os.getenv('ADMIN_DEFAULT_USER')
        pwd = os.getenv('ADMIN_DEFAULT_PASS')
        nombre = os.getenv('ADMIN_DEFAULT_NOMBRE', 'Admin Inicial')
        if user and pwd:
            if not Administrador.query.filter_by(usuario=user).first():
                db.session.add(Administrador(usuario=user, password=pwd, nombre=nombre, rol='super'))
                db.session.commit()
                print(f"[SEED] Administrador creado: {user}")
            else:
                print('[SEED] Admin inicial ya existe, no se crea otro.')
    except Exception as e:
        print('[SEED] Error creando admin inicial:', e)

with app.app_context():
    ensure_seed_admin()
    # Normalizar imágenes antiguas que guardaron ruta completa
    try:
        from models import MenuItem
        cambios = 0
        for mi in MenuItem.query.all():
            if mi.imagen and '/static/uploads/' in mi.imagen:
                import os as _os
                nuevo = _os.path.basename(mi.imagen)
                if nuevo != mi.imagen:
                    mi.imagen = nuevo
                    cambios += 1
        if cambios:
            db.session.commit()
            print(f"[NORMALIZACION] Imágenes ajustadas: {cambios}")
    except Exception as _e_norm:
        print('[NORMALIZACION] Aviso al limpiar imágenes:', _e_norm)

    # Registro automático de webhook (solo una vez al arrancar el proceso principal)
    try:
        # Condiciones: tener TOKEN, no usar polling explícito y bandera TELEGRAM_AUTO_WEBHOOK=1
        if TELEGRAM_TOKEN and os.getenv('TELEGRAM_USE_POLLING', '0') != '1' and os.getenv('TELEGRAM_AUTO_WEBHOOK', '1') == '1':
            # Base pública: prioridad a TELEGRAM_WEBHOOK_BASE, luego RENDER_EXTERNAL_URL, luego PUBLIC_BASE_URL
            public_base = os.getenv('TELEGRAM_WEBHOOK_BASE') or os.getenv('PUBLIC_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL')
            if public_base:
                public_base = public_base.rstrip('/')
                webhook_url = f"{public_base}/telegram/webhook"
                import requests as _r
                resp = _r.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook', params={'url': webhook_url, 'max_connections': 40})
                j = {}
                try:
                    j = resp.json()
                except Exception:
                    pass
                if j.get('ok'):
                    print(f"[TELEGRAM] Webhook registrado auto -> {webhook_url}")
                else:
                    print(f"[TELEGRAM] Falló auto setWebhook status={resp.status_code} body={resp.text[:200]}")
            else:
                print('[TELEGRAM] No se pudo registrar webhook automáticamente: falta TELEGRAM_WEBHOOK_BASE o RENDER_EXTERNAL_URL')
    except Exception as _e_auto_wh:
        print('[TELEGRAM] Error registrando webhook auto:', _e_auto_wh)

# Iniciar polling en desarrollo (solo si no hay variable que indique producción)
try:
    # En producción (Render) se recomienda usar webhook; desactivar polling por defecto (valor '0').
    if os.environ.get('TELEGRAM_USE_POLLING', '0') == '1':
        # Evitar doble arranque en recarga debug
        if TELEGRAM_TOKEN and os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            iniciar_polling_background(app)
            print('[TELEGRAM] Polling background iniciado (main)')
        elif not TELEGRAM_TOKEN:
            print('[TELEGRAM] Polling no iniciado: falta TELEGRAM_TOKEN')
        else:
            print('[TELEGRAM] Polling omitido (proceso secundario reloader)')
except Exception as _e:
    print('[TELEGRAM] No se pudo iniciar polling background:', _e)

@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = request.get_json(force=True, silent=True) or {}
        print('[TELEGRAM] Update recibido:', update)
        procesar_update(update)
    except Exception as e:
        print('[TELEGRAM] Error webhook:', e)
    return jsonify({'ok': True})

@app.route('/telegram/set_webhook')
def set_webhook():
    """Helper rápido para registrar el webhook (usar temporalmente)."""
    # URL pública donde está accesible tu servidor (reemplazar)
    public_url = request.args.get('url')  # ?url=https://tu-dominio
    if not public_url:
        return 'Proporciona ?url=https://tu-dominio', 400
    import requests as _r
    resp = _r.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook', params={'url': f'{public_url}/telegram/webhook'})
    return resp.text, resp.status_code

@app.route('/telegram/delete_webhook')
def delete_webhook():
    import requests as _r
    resp = _r.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook')
    return resp.text, resp.status_code

@app.route('/telegram/webhook_info')
def webhook_info():
    """Devuelve info del webhook actual para debugging."""
    if not TELEGRAM_TOKEN:
        return jsonify({'ok': False, 'error': 'Sin TELEGRAM_TOKEN'}), 400
    import requests as _r
    r = _r.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo', timeout=10)
    try:
        data = r.json()
    except Exception:
        data = {'ok': False, 'error': 'Respuesta no JSON', 'raw': r.text[:200]}
    return jsonify(data), 200 if data.get('ok') else 500

@app.route('/telegram/force_webhook')
def force_webhook():
    """Fuerza setWebhook usando base de env. Protegido opcionalmente por TELEGRAM_WEBHOOK_SECRET."""
    secret_cfg = os.getenv('TELEGRAM_WEBHOOK_SECRET')
    secret_req = request.args.get('secret')
    if secret_cfg and secret_cfg != secret_req:
        return 'Forbidden', 403
    if not TELEGRAM_TOKEN:
        return 'Falta TELEGRAM_TOKEN', 400
    base = request.args.get('base') or os.getenv('TELEGRAM_WEBHOOK_BASE') or os.getenv('PUBLIC_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL')
    if not base:
        return 'Falta base (?base=https://... o TELEGRAM_WEBHOOK_BASE)', 400
    base = base.rstrip('/')
    full_url = f"{base}/telegram/webhook"
    import requests as _r
    r = _r.get(f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook', params={'url': full_url})
    return r.text, r.status_code

@app.route('/telegram/poll')
def telegram_poll():
    """Procesa manualmente updates (usar si no configuraste webhook)."""
    res = poll_once()
    return jsonify(res)

@app.route('/pedido', methods=['GET', 'POST'])
def pedido_cliente():
    establecimientos = Sucursal.query.all()
    productos = MenuItem.query.all()
    
    # Añadir información de horarios a los establecimientos
    establecimientos_data = []
    for establecimiento in establecimientos:
        # Verificar si está abierto ahora
        abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(establecimiento.id)
        
        # Obtener horarios para mostrar
        horarios_info = []
        for horario in establecimiento.horarios:
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            if horario.cerrado:
                horarios_info.append(f"{dias[horario.dia_semana]}: Cerrado")
            else:
                horarios_info.append(f"{dias[horario.dia_semana]}: {horario.hora_apertura.strftime('%H:%M')} - {horario.hora_cierre.strftime('%H:%M')}")
        
        establecimientos_data.append({
            'id': establecimiento.id,
            'nombre': establecimiento.nombre,
            'direccion': establecimiento.direccion,
            'telefono': establecimiento.telefono,
            'activa': establecimiento.activa,
            'abierta_ahora': abierta_ahora,
            'horarios': horarios_info
        })
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        direccion = request.form['direccion']
        establecimiento_id = int(request.form['sucursal_id'])  # Mantenemos el nombre del campo HTML por compatibilidad
        productos_seleccionados = request.form.getlist('productos')
        total = float(request.form['total'])
        
        # Validar que el establecimiento esté abierto
        establecimiento = Sucursal.query.get(establecimiento_id)
        if not establecimiento or not establecimiento.activa:
            flash('El establecimiento seleccionado no está disponible.', 'danger')
            template_name = 'pedido_cliente_mobile.html' if is_mobile_device() else 'pedido_cliente_desktop.html'
            return render_template(template_name, sucursales=establecimientos_data, productos=productos)
        
        abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(establecimiento_id)
        if not abierta_ahora:
            flash('El establecimiento seleccionado está cerrado en este momento. Por favor verifica los horarios de atención.', 'warning')
            template_name = 'pedido_cliente_mobile.html' if is_mobile_device() else 'pedido_cliente_desktop.html'
            return render_template(template_name, sucursales=establecimientos_data, productos=productos)
        
        productos_str = ', '.join(productos_seleccionados)
        pedido = PedidoCliente(
            nombre=nombre,
            telefono=telefono,
            direccion=direccion,
            sucursal_id=establecimiento_id,  # Mantenemos el nombre del campo DB por compatibilidad
            productos=productos_str,
            total=total,
            fecha=datetime.now(),
            estado='Pendiente'
        )
        db.session.add(pedido)
        db.session.commit()
        flash('¡Pedido realizado correctamente! Pronto nos pondremos en contacto.', 'success')
        return redirect(url_for('pedido_cliente'))
    
    template_name = 'pedido_cliente_mobile.html' if is_mobile_device() else 'pedido_cliente_desktop.html'
    return render_template(template_name, sucursales=establecimientos_data, productos=productos)

@app.route('/')
def index():
    """Página de inicio profesional con categorías"""
    categorias = Categoria.query.all()
    establecimientos_query = Sucursal.query.filter_by(activa=True).all()
    productos_destacados = MenuItem.query.limit(6).all()
    
    # Añadir información de horarios a los establecimientos para el index
    establecimientos_data = []
    for establecimiento in establecimientos_query:
        # Verificar si está abierto ahora
        abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(establecimiento.id)
        
        # Obtener horarios para mostrar
        horarios_info = []
        for horario in establecimiento.horarios:
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            if horario.cerrado:
                horarios_info.append(f"{dias[horario.dia_semana]}: Cerrado")
            else:
                horarios_info.append(f"{dias[horario.dia_semana]}: {horario.hora_apertura.strftime('%H:%M')} - {horario.hora_cierre.strftime('%H:%M')}")
        
        establecimientos_data.append({
            'id': establecimiento.id,
            'nombre': establecimiento.nombre,
            'direccion': establecimiento.direccion,
            'telefono': establecimiento.telefono,
            'activa': establecimiento.activa,
            'abierta_ahora': abierta_ahora,
            'horarios': horarios_info
        })
    
    # Determinar template según dispositivo
    if is_mobile_device():
        template_name = 'index_mobile.html'
        print("📱 Sirviendo índice móvil")
    else:
        template_name = 'index_desktop.html'
        print("💻 Sirviendo índice escritorio")
    
    return render_template(template_name, 
                         categorias=categorias, 
                         establecimientos=establecimientos_data,
                         productos_destacados=productos_destacados)

@app.route('/catalogo')
def catalogo():
    establecimientos = Sucursal.query.all()
    categorias = Categoria.query.all()
    productos = MenuItem.query.all()
    
    # Añadir información de horarios a los establecimientos
    establecimientos_data = []
    for establecimiento in establecimientos:
        # Verificar si está abierto ahora
        abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(establecimiento.id)
        
        # Obtener horarios para mostrar
        horarios_info = []
        for horario in establecimiento.horarios:
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            if horario.cerrado:
                horarios_info.append(f"{dias[horario.dia_semana]}: Cerrado")
            else:
                horarios_info.append(f"{dias[horario.dia_semana]}: {horario.hora_apertura.strftime('%H:%M')} - {horario.hora_cierre.strftime('%H:%M')}")
        
        establecimientos_data.append({
            'id': establecimiento.id,
            'nombre': establecimiento.nombre,
            'direccion': establecimiento.direccion,
            'telefono': establecimiento.telefono,
            'activa': establecimiento.activa,
            'abierta_ahora': abierta_ahora,
            'horarios': horarios_info
        })

    # Procesar categorías con conteos
    categorias_data = []
    for cat in categorias:
        productos_count = len([p for p in productos if p.categoria_id == cat.id])
        categorias_data.append({
            'id': cat.id,
            'nombre': cat.nombre,
            'icono': '🍽️',  # Icono por defecto
            'productos_count': productos_count
        })
    
    productos_data = []
    for p in productos:
        sucursales_ids = [str(rel.sucursal_id) for rel in p.sucursales if rel.disponible]
        
        # Procesar opciones personalizadas
        opciones = []
        for op in p.opciones:
            valores = []
            for val in op.valores:
                valores.append({
                    "id": val.id,
                    "nombre": val.texto,
                    "precio_adicional": val.precio or 0
                })
            opciones.append({
                "id": op.id,
                "nombre": op.titulo,
                "descripcion": "",  # No hay descripción en el modelo
                "es_obligatoria": op.obligatorio,
                "tipo": op.tipo,
                "valores": valores
            })
        
        # Generar imagen URL si existe
        imagen_url = None
        if p.imagen:
            # Si ya es URL absoluta (http/https) la usamos tal cual
            if isinstance(p.imagen, str) and (p.imagen.startswith('http://') or p.imagen.startswith('https://')):
                imagen_url = p.imagen
            else:
                # p.imagen debe ser un filename limpio (normalizado). Si accidentalmente contiene '/static/uploads/', lo limpiamos.
                filename = p.imagen.split('/static/uploads/')[-1]
                filename = filename.replace('uploads/','')  # por si ya incluye prefijo
                imagen_url = url_for('static', filename=f'uploads/{filename}')
        
        productos_data.append({
            "id": p.id,
            "nombre": p.nombre,
            "imagen_url": imagen_url,
            "descripcion": p.descripcion,
            "precio": p.precio,  # Usar el precio real de la base de datos
            "categoria_id": p.categoria_id,
            "categoria_nombre": p.categoria.nombre if p.categoria else "Sin categoría",
            "opciones": opciones,
            "sucursales": sucursales_ids
        })

    print("PRODUCTOS:", productos_data)  # Para verificar que ya tienen precio
    
    # Determinar template según dispositivo
    if is_mobile_device():
        template_name = 'catalogo_mobile.html'
        print("📱 Sirviendo catálogo móvil")
    else:
        template_name = 'catalogo_desktop.html'
        print("💻 Sirviendo catálogo escritorio")
    
    return render_template(template_name, productos=productos_data, sucursales=establecimientos_data, categorias=categorias_data)

@app.route('/agregar_carrito', methods=['POST'])
def agregar_carrito():
    print("=== AGREGAR CARRITO DEBUG ===")
    
    # Verificar si es un request JSON (móvil) o form data (escritorio)
    if request.is_json:
        data = request.get_json()
        es_desktop_json = request.headers.get('X-Desktop') == '1'
        print("🛎️ Request JSON recibido (desktop_json=", es_desktop_json, "):", data)

        producto_id = data.get('producto_id')
        cantidad = data.get('cantidad', 1)
        opciones = data.get('opciones', {})  # dict opcion_id -> [valor_ids]

        producto = MenuItem.query.get(int(producto_id))
        if not producto:
            return jsonify({'success': False, 'error': 'Producto no encontrado'}), 404

        if es_desktop_json:
            # Procesar como escritorio: construir estructura de opciones seleccionadas con precios
            opciones_seleccionadas = []
            precio_extra_total = 0.0
            for opcion_id, valores_ids in opciones.items():
                try:
                    opcion_model = OpcionPersonalizada.query.get(int(opcion_id))
                except Exception:
                    opcion_model = None
                if not opcion_model:
                    continue
                for valor_id in valores_ids:
                    valor_model = ValorOpcion.query.get(int(valor_id))
                    if valor_model:
                        precio_adicional = float(valor_model.precio or 0)
                        precio_extra_total += precio_adicional
                        opciones_seleccionadas.append({
                            'opcion_id': opcion_model.id,
                            'opcion_titulo': opcion_model.titulo,
                            'valor_id': valor_model.id,
                            'valor_texto': valor_model.texto,
                            'precio': precio_adicional
                        })
            carrito = session.get('carrito', [])
            carrito.append({
                'producto_id': producto_id,
                'cantidad': cantidad,
                'extras': [],
                'opciones_personalizadas': opciones_seleccionadas,
                'precio_extra_total': precio_extra_total,
                'precio': float(producto.precio)
            })
            session['carrito'] = carrito
            print("💻 Carrito actualizado (JSON escritorio)", carrito)
            return jsonify({'success': True, 'carrito_cantidad': len(carrito)})
        else:
            # Móvil: no persiste en backend
            return jsonify({
                'success': True,
                'producto': {
                    'nombre': producto.nombre,
                    'precio': float(producto.precio)
                }
            })
    
    else:
        # Request form data desde escritorio
        print("💻 Request form escritorio")
        print("Form data:", dict(request.form))
        print("Form data completo (con listas):", request.form.to_dict(flat=False))
        
        producto_id = request.form['producto_id']
        cantidad = int(request.form.get('cantidad', 1))
        
        print(f"Producto ID: {producto_id}, Cantidad: {cantidad}")
        
        # Obtener el producto
        producto = MenuItem.query.get(int(producto_id))
        if not producto:
            print("❌ Producto no encontrado")
            return redirect(url_for('catalogo'))
        
        print(f"✅ Producto encontrado: {producto.nombre}")
        print(f"📋 Opciones del producto: {len(producto.opciones)} opciones")
        
        # Procesar opciones personalizadas para escritorio
        opciones_seleccionadas = []
        precio_extra_total = 0
        
        # Iterar sobre todas las opciones del producto
        for opcion in producto.opciones:
            nombre_campo = f"opcion_{opcion.id}"
            nombre_campo_checkbox = f"opcion_{opcion.id}[]"
            print(f"🔍 Buscando campo: {nombre_campo} (tipo: {opcion.tipo})")
            
            if opcion.tipo == "checkbox":
                print(f"🔍 También buscando: {nombre_campo_checkbox} para checkboxes")
                valores_seleccionados = request.form.getlist(nombre_campo_checkbox)
                if not valores_seleccionados:
                    # Fallback: buscar sin []
                    valores_seleccionados = request.form.getlist(nombre_campo)
                    print(f"📝 Fallback - valores sin []: {valores_seleccionados}")
            else:
                valores_seleccionados = [request.form.get(nombre_campo)]
            
            print(f"📝 Valores encontrados: {valores_seleccionados}")
            
            for valor_seleccionado in valores_seleccionados:
                if valor_seleccionado:
                    print(f"✅ Procesando valor: {valor_seleccionado}")
                    # Buscar el valor de opción correspondiente
                    for valor_opcion in opcion.valores:
                        # Comparar con el ID del valor
                        if str(valor_opcion.id) == str(valor_seleccionado):
                            opciones_seleccionadas.append({
                                'opcion_id': opcion.id,
                                'opcion_titulo': opcion.titulo,
                                'valor_id': valor_opcion.id,
                                'valor_texto': valor_opcion.texto,
                                'valor_precio': valor_opcion.precio or 0
                            })
                            precio_extra_total += (valor_opcion.precio or 0)
                            print(f"✅ Opción agregada: {valor_opcion.texto} (+${valor_opcion.precio or 0})")
                            break
        
        print(f"💰 Precio extra total: ${precio_extra_total}")
        print(f"📦 Opciones seleccionadas: {len(opciones_seleccionadas)}")
        
        # Procesar extras (sistema anterior)
        extras = request.form.getlist('extras')
        
        carrito = session.get('carrito', [])
        item_carrito = {
            'producto_id': producto_id,
            'extras': extras,
            'cantidad': cantidad,
            'opciones_personalizadas': opciones_seleccionadas,
            'precio_extra_total': precio_extra_total,
            # Guardamos precio base para que /get_carrito_estado no dependa de recalcular
            'precio': float(producto.precio)
        }
        carrito.append(item_carrito)
        session['carrito'] = carrito
        
        print(f"🛒 Item agregado al carrito: {item_carrito}")
        print(f"🛒 Total items en carrito: {len(carrito)}")
        print("=== FIN DEBUG ===")
        
        # Guardar información del producto agregado para el toast
        session['producto_agregado'] = {
            'nombre': producto.nombre,
            'imagen': producto.imagen,
            'precio': producto.precio + precio_extra_total,
            'cantidad': cantidad
        }
        
        return redirect(url_for('catalogo', agregado=1))

@app.route('/get_producto_agregado')
def get_producto_agregado():
    """Obtener información del último producto agregado para el toast"""
    producto_info = session.get('producto_agregado', {})
    
    # Limpiar la información después de obtenerla
    if 'producto_agregado' in session:
        del session['producto_agregado']
    
    return jsonify(producto_info)

@app.route('/get_carrito_estado')
def get_carrito_estado():
    """Obtener el estado actual del carrito (cantidad y total) para actualizar el header"""
    carrito = session.get('carrito', [])
    print('🔎 DEBUG get_carrito_estado - contenido carrito:', carrito)
    
    total_cantidad = 0
    total_precio = 0.0
    
    for item in carrito:
        cantidad = item.get('cantidad', 1)
        total_cantidad += cantidad

        # Precio base: usar guardado; si no existe, consultar DB (compatibilidad items antiguos)
        if 'precio' in item:
            precio_base = float(item.get('precio', 0))
        else:
            try:
                prod = MenuItem.query.get(int(item.get('producto_id')))
                precio_base = float(prod.precio) if prod else 0.0
            except Exception:
                precio_base = 0.0

        # Precios de opciones personalizadas (nueva estructura) o acumulado legacy
        precio_opciones = 0.0
        opciones = item.get('opciones_personalizadas', [])
        for opcion in opciones:
            precio_opciones += float(opcion.get('precio', 0))

        # Compatibilidad: some flows stored precio_extra_total
        precio_extra_total = float(item.get('precio_extra_total', 0))
        # Solo usar precio_extra_total si no hay lista detallada de opciones
        if precio_extra_total and not opciones:
            precio_opciones += precio_extra_total

        precio_total_item = (precio_base + precio_opciones) * cantidad
        total_precio += precio_total_item
    
    return jsonify({
        'cantidad': total_cantidad,
        'total': total_precio,
        'total_formateado': f'${total_precio:.2f}'
    })

@app.route('/carrito')
def carrito():
    carrito = session.get('carrito', [])
    productos = []
    total = 0
    indices_invalidos = []
    for idx, item in enumerate(carrito):
        try:
            prod_id = int(item.get('producto_id'))
        except Exception:
            indices_invalidos.append(idx)
            continue
        producto = MenuItem.query.get(prod_id)
        if not producto:
            # Registrar para limpieza; probablemente el producto fue eliminado de la base de datos
            indices_invalidos.append(idx)
            continue
        extras_objs = [Extra.query.get(int(eid)) for eid in item.get('extras', [])]
        # Calcular precio base (precio vigente en DB * cantidad guardada)
        try:
            cantidad = int(item.get('cantidad', 1))
        except Exception:
            cantidad = 1
        precio_base = float(producto.precio) * cantidad
        # Agregar precio de extras (sistema anterior)
        precio_extras = sum([e.precio for e in extras_objs if e])
        # Agregar precio de opciones personalizadas (estructura nueva)
        precio_opciones = float(item.get('precio_extra_total', 0) or 0) * cantidad
        subtotal = precio_base + precio_extras + precio_opciones
        productos.append({
            'producto': producto,
            'extras': extras_objs,
            'cantidad': cantidad,
            'subtotal': subtotal,
            'opciones_personalizadas': [
                {
                    **op,
                    'precio': float(op.get('precio', op.get('valor_precio', 0) or 0))
                } for op in item.get('opciones_personalizadas', [])
            ],
            'precio_opciones': precio_opciones
        })
        total += subtotal

    # Limpiar items inválidos del carrito si los hay
    if indices_invalidos:
        # Eliminar desde el final para no alterar índices intermedios
        for i in sorted(indices_invalidos, reverse=True):
            try:
                carrito.pop(i)
            except Exception:
                pass
        session['carrito'] = carrito
        session.modified = True
        if not productos:
            flash('Algunos productos ya no están disponibles y fueron removidos del carrito.', 'warning')
    
    # Determinar template según dispositivo
    if is_mobile_device():
        template_name = 'carrito_mobile.html'
        print("📱 Sirviendo carrito móvil")
    else:
        template_name = 'carrito_desktop.html'
        print("💻 Sirviendo carrito escritorio")
    
    return render_template(template_name, productos=productos, total=total)

@app.route('/limpiar_carrito', methods=['POST'])
def limpiar_carrito():
    """Limpiar todo el carrito"""
    session['carrito'] = []
    return redirect(url_for('carrito'))

@app.route('/sincronizar_carrito', methods=['POST'])
def sincronizar_carrito():
    """Sincroniza el carrito enviado desde móvil (localStorage) al backend para reutilizar vistas server-side."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        items = data.get('items', [])
        carrito_convertido = []
        for raw in items:
            producto_id = raw.get('producto_id') or raw.get('id')
            if not producto_id:
                continue
            # Opciones: pueden venir en 'opciones_personalizadas' (nombre, precio) o en 'opciones' (lista con precio_adicional)
            opciones_list = []
            if isinstance(raw.get('opciones_personalizadas'), list):
                for op in raw['opciones_personalizadas']:
                    opciones_list.append({
                        'opcion_id': op.get('opcion_id'),  # puede ser None en móvil
                        'opcion_titulo': op.get('opcion_titulo'),
                        'valor_id': op.get('id'),
                        'valor_texto': op.get('valor_texto') or op.get('nombre'),
                        'precio': float(op.get('precio', op.get('precio_adicional', 0) or 0))
                    })
            elif isinstance(raw.get('opciones'), list):
                for op in raw['opciones']:
                    opciones_list.append({
                        'valor_id': op.get('id'),
                        'valor_texto': op.get('nombre'),
                        'precio': float(op.get('precio_adicional', 0) or 0)
                    })
            precio_base = float(raw.get('precio_base', raw.get('precio', 0) or 0))
            cantidad = int(raw.get('cantidad', 1))
            precio_extra_total = sum(o.get('precio', 0) for o in opciones_list)
            carrito_convertido.append({
                'producto_id': producto_id,
                'cantidad': cantidad,
                'extras': [],
                'opciones_personalizadas': opciones_list,
                'precio_extra_total': precio_extra_total,
                'precio': precio_base
            })
        session['carrito'] = carrito_convertido
        session.modified = True
        print('🔄 Sincronización carrito móvil -> sesión:', carrito_convertido)
        return jsonify({'success': True, 'items': len(carrito_convertido)})
    except Exception as e:
        print('❌ Error sincronizando carrito móvil:', e)
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/cambiar_cantidad_item', methods=['POST'])
def cambiar_cantidad_item():
    """Cambiar cantidad de un item específico en el carrito"""
    indice = int(request.form.get('indice'))
    delta = int(request.form.get('delta'))
    
    carrito = session.get('carrito', [])
    
    if 0 <= indice < len(carrito):
        nueva_cantidad = max(1, carrito[indice]['cantidad'] + delta)
        carrito[indice]['cantidad'] = nueva_cantidad
        session['carrito'] = carrito
    
    return redirect(url_for('carrito'))

@app.route('/eliminar_item', methods=['POST'])
def eliminar_item():
    """Eliminar un item específico del carrito"""
    indice = int(request.form.get('indice'))
    
    carrito = session.get('carrito', [])
    
    if 0 <= indice < len(carrito):
        carrito.pop(indice)
        session['carrito'] = carrito
    
    return redirect(url_for('carrito'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    # Log de versión para confirmar que esta versión del código está activa
    print(f"[CHECKOUT] Versión código: {CODE_VERSION}")
    if request.method == 'POST':
        # Verificar si es una confirmación de pedido (tiene datos del formulario)
        if 'nombre' in request.form:
            # Es la confirmación del pedido
            nombre = request.form['nombre']
            telefono = request.form['telefono']
            calle = request.form['calle']
            numero = request.form['numero']
            colonia = request.form['colonia']
            entre_calles = request.form['entre_calles']
            referencia = request.form['referencia']
            
            # Datos de pago
            forma_pago = request.form['forma_pago']
            cambio_para = request.form.get('cambio_para')
            confirmo_transferencia = 'confirmo_transferencia' in request.form
            
            # Convertir cambio_para a float si existe
            cambio_para_float = None
            if cambio_para and cambio_para.strip():
                try:
                    cambio_para_float = float(cambio_para)
                except ValueError:
                    cambio_para_float = None
            
            # Construir dirección completa
            direccion = f"Calle: {calle}, Número: {numero}, Colonia: {colonia}, Entre: {entre_calles}, Referencia: {referencia}"
            
            # Obtener sucursal: puede faltar si el form no incluyó select (bug móvil)
            sucursal_id_raw = request.form.get('sucursal_id')
            if not sucursal_id_raw:
                # Intentar derivar de carrito_data (cada item podría tener sucursal_id en el futuro) o usar último en session
                try:
                    if 'carrito_data' in request.form:
                        cd = json.loads(request.form['carrito_data'])
                        # Buscar clave sucursal_id en items
                        for it in cd:
                            if 'sucursal_id' in it:
                                sucursal_id_raw = it['sucursal_id']
                                break
                except Exception:
                    pass
            if not sucursal_id_raw:
                # Fallback: usar sucursal 1 (documentar) y avisar
                sucursal_id_raw = 1
                flash('No se recibió la sucursal, se asignó la sucursal #1 por defecto.', 'warning')
            try:
                sucursal_id = int(sucursal_id_raw)
            except (TypeError, ValueError):
                flash('Sucursal inválida.', 'danger')
                return redirect(url_for('checkout'))
            total = float(request.form['total'])
            
            # VALIDAR QUE LA SUCURSAL ESTÉ ABIERTA
            sucursal = Sucursal.query.get(sucursal_id)
            if not sucursal or not sucursal.activa:
                flash('La sucursal seleccionada no está disponible.', 'danger')
                return redirect(url_for('checkout'))
            
            abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(sucursal_id)
            if not abierta_ahora:
                flash('La sucursal seleccionada está cerrada en este momento. Por favor verifica los horarios de atención.', 'warning')
                return redirect(url_for('checkout'))
            
            # Procesar productos del carrito
            productos_detallados = []
            
            # Verificar si viene información del carrito en el request
            if 'carrito_data' in request.form:
                # Viene del carrito de localStorage con JSON
                try:
                    carrito_data = json.loads(request.form['carrito_data'])
                    for item in carrito_data:
                        producto = MenuItem.query.get(int(item['id']))
                        if producto:
                            cantidad = int(item.get('cantidad', 1))
                            opciones_raw = item.get('opciones_personalizadas') or item.get('opciones') or []
                            opciones_list = []  # Lista de strings para almacenar texto (+precio)
                            costo_opciones = 0.0
                            for opcion in opciones_raw:
                                # Texto tolerante a diferentes claves
                                texto = opcion.get('texto') or opcion.get('valor_texto') or opcion.get('nombre') or 'Opción'
                                # Precio adicional tolerante a diferentes claves
                                precio_add = opcion.get('precio')
                                if precio_add is None:
                                    precio_add = opcion.get('precio_adicional')
                                try:
                                    precio_add_float = float(precio_add) if precio_add not in (None, "", False) else 0.0
                                except (TypeError, ValueError):
                                    precio_add_float = 0.0
                                if precio_add_float > 0:
                                    opciones_list.append(f"{texto} (+${precio_add_float:.2f})")
                                    costo_opciones += precio_add_float * cantidad
                                else:
                                    opciones_list.append(texto)

                            subtotal = producto.precio * cantidad + costo_opciones
                            productos_detallados.append({
                                'id': producto.id,
                                'nombre': producto.nombre,
                                'cantidad': cantidad,
                                'precio_unitario': producto.precio,  # Base sin extras
                                'precio_total': subtotal,
                                'opciones_personalizadas': opciones_list
                            })
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
            
            # Si no hay productos detallados, usar el string del formulario tradicional
            if not productos_detallados:
                productos_str = request.form.get('productos_str', '')
                if productos_str:
                    # Crear entrada básica desde string simple
                    productos_detallados.append({
                        'id': 0,
                        'nombre': productos_str,
                        'cantidad': 1,
                        'precio_unitario': total,
                        'precio_total': total,
                        'opciones_personalizadas': []
                    })

            # Fallback adicional: reconstruir desde carrito de sesión si sigue vacío
            if not productos_detallados:
                carrito_session = session.get('carrito', [])
                reconstruidos = []
                for item in carrito_session:
                    try:
                        prod_id = int(item.get('producto_id') or 0)
                    except (TypeError, ValueError):
                        continue
                    prod = MenuItem.query.get(prod_id)
                    if not prod:
                        continue
                    cantidad = int(item.get('cantidad', 1) or 1)
                    # Opciones personalizadas en sesión
                    opciones = []
                    for op in item.get('opciones_personalizadas', []):
                        texto = op.get('valor_texto') or op.get('texto') or op.get('nombre') or op.get('opcion_titulo') or 'Opción'
                        precio_op = op.get('precio')
                        if precio_op is None:
                            precio_op = op.get('valor_precio')
                        try:
                            precio_op_float = float(precio_op) if precio_op not in (None, '', False) else 0.0
                        except (TypeError, ValueError):
                            precio_op_float = 0.0
                        if precio_op_float > 0:
                            opciones.append(f"{texto} (+${precio_op_float:.2f})")
                        else:
                            opciones.append(texto)
                    # Calcular subtotal
                    precio_base = float(prod.precio) * cantidad
                    # Sumar precios de opciones si estaban acumulados
                    extra_total = 0.0
                    for op in item.get('opciones_personalizadas', []):
                        p_val = op.get('precio') or op.get('valor_precio') or 0
                        try:
                            p_val = float(p_val)
                        except (TypeError, ValueError):
                            p_val = 0.0
                        if p_val > 0:
                            extra_total += p_val * cantidad
                    subtotal = precio_base + extra_total
                    reconstruidos.append({
                        'id': prod.id,
                        'nombre': prod.nombre,
                        'cantidad': cantidad,
                        'precio_unitario': float(prod.precio),
                        'precio_total': subtotal,
                        'opciones_personalizadas': opciones
                    })
                if reconstruidos:
                    productos_detallados = reconstruidos
                    print('[CHECKOUT] Fallback productos desde sesión aplicado:', productos_detallados)
                else:
                    print('[CHECKOUT] Advertencia: productos_detallados vacío; se guardará lista vacía.')
            
            # Generar número de pedido único
            numero_pedido = generar_numero_pedido()
            
            pedido = PedidoCliente(
                numero_pedido=numero_pedido,
                nombre=nombre,
                telefono=telefono,
                direccion=direccion,
                calle=calle,
                numero=numero,
                colonia=colonia,
                entre_calles=entre_calles,
                referencia=referencia,
                sucursal_id=sucursal_id,
                productos=json.dumps(productos_detallados),  # Guardar como JSON detallado
                total=total,
                fecha=datetime.now(),
                estado='Pendiente',
                forma_pago=forma_pago,
                cambio_para=cambio_para_float,
                comprobante_transferencia=confirmo_transferencia
            )
            db.session.add(pedido)
            db.session.commit()
            print('[CHECKOUT] Pedido guardado con productos JSON len=', len(productos_detallados))
            
            # Enviar notificación de Telegram al admin
            try:
                enviar_notificacion_pedido(pedido)
                print(f"✅ Notificación enviada para pedido {numero_pedido}")
            except Exception as e:
                print(f"❌ Error al enviar notificación de Telegram: {e}")
                # No fallar el pedido si Telegram falla
            
            # Guardar el número de pedido en la sesión para mostrarlo en la confirmación
            session['ultimo_numero_pedido'] = numero_pedido
            # Guardar la sucursal del pedido para limpiar carrito localStorage en confirmación (móvil multi-sucursal)
            session['ultima_sucursal_pedido'] = sucursal_id
            
            # Limpiar el carrito de sesión después de confirmar el pedido
            session.pop('carrito', None)
            
            return redirect(url_for('confirmacion'))
        
        # Si es un POST desde el carrito con carrito_data pero sin formulario completo
        elif 'carrito_data' in request.form:
            carrito_data = json.loads(request.form['carrito_data'])
            sucursal_id = request.form['sucursal_id']
            
            # Debug: Imprimir estructura de datos
            print("DEBUG - Carrito data:", carrito_data)
            
            # Procesar el carrito del localStorage
            productos = []
            total = 0
            # Normalización de items del carrito provenientes de móvil (localStorage) o escritorio (sesión)
            # Esquemas posibles para opciones:
            #  - {'texto': 'Sin cebolla', 'precio': 0}
            #  - {'valor_texto': 'Grande', 'precio': 15}
            #  - {'nombre': 'Extra queso', 'precio_adicional': 10}
            # Siempre usaremos 'texto' interno y recalcularemos el costo con precio de DB del producto base.
            for item in carrito_data:
                try:
                    prod_id = int(item.get('id') or item.get('producto_id'))
                except (TypeError, ValueError):
                    continue
                producto = MenuItem.query.get(prod_id)
                if not producto:
                    continue
                cantidad_item = int(item.get('cantidad', 1))
                # Precio base por unidad del producto desde DB (no confiar en cliente)
                subtotal_base = producto.precio * cantidad_item
                opciones_costo = 0.0
                opciones_info = []
                opciones_raw = item.get('opciones_personalizadas') or item.get('opciones') or []
                print(f"DEBUG - Opciones para {producto.nombre} (normalizadas):", opciones_raw)
                for opcion in opciones_raw:
                    # Extraer texto y precio unitario tolerando múltiples esquemas
                    texto = opcion.get('texto') or opcion.get('valor_texto') or opcion.get('nombre') or 'Opción'
                    precio_unit_add = opcion.get('precio')
                    if precio_unit_add is None:
                        precio_unit_add = opcion.get('precio_adicional')
                    try:
                        precio_unit_add = float(precio_unit_add) if precio_unit_add else 0.0
                    except (TypeError, ValueError):
                        precio_unit_add = 0.0
                    if precio_unit_add > 0:
                        opciones_costo += precio_unit_add * cantidad_item
                        opciones_info.append(f"{texto} (+${precio_unit_add:.2f})")
                    else:
                        opciones_info.append(texto)
                subtotal = subtotal_base + opciones_costo
                print(f"DEBUG - {producto.nombre}: base=${producto.precio:.2f} x{cantidad_item}, opciones=${opciones_costo:.2f}, subtotal=${subtotal:.2f}")
                productos.append({
                    'producto': producto,
                    'cantidad': cantidad_item,
                    'subtotal': subtotal,
                    'opciones_info': opciones_info
                })
                total += subtotal
            
            print(f"DEBUG - Total calculado: ${total:.2f}")
            
            sucursales = Sucursal.query.all()
            # Añadir información de horarios a las sucursales
            sucursales_data = []
            for sucursal in sucursales:
                # Verificar si está abierta ahora
                abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(sucursal.id)
                
                # Obtener horarios para mostrar
                horarios_info = []
                for horario in sucursal.horarios:
                    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                    if horario.cerrado:
                        horarios_info.append(f"{dias[horario.dia_semana]}: Cerrado")
                    else:
                        horarios_info.append(f"{dias[horario.dia_semana]}: {horario.hora_apertura.strftime('%H:%M')} - {horario.hora_cierre.strftime('%H:%M')}")
                
                sucursales_data.append({
                    'id': sucursal.id,
                    'nombre': sucursal.nombre,
                    'direccion': sucursal.direccion,
                    'telefono': sucursal.telefono,
                    'activa': sucursal.activa,
                    'abierta_ahora': abierta_ahora,
                    'horarios': horarios_info
                })
            
            sucursal_actual = Sucursal.query.get(int(sucursal_id)) if sucursal_id else None
            
            # Determinar template según dispositivo
            if is_mobile_device():
                template_name = 'checkout_mobile.html'
                print("📱 Sirviendo checkout móvil")
            else:
                template_name = 'checkout_desktop.html'
                print("💻 Sirviendo checkout escritorio")
            
            return render_template(template_name, productos=productos, total=total, sucursales=sucursales_data, sucursal_actual=sucursal_actual)
    
    # GET request - mostrar carrito desde session (método anterior)
    carrito = session.get('carrito', [])
    if not carrito:
        return redirect(url_for('catalogo'))
    
    sucursales = Sucursal.query.all()
    
    # Añadir información de horarios a las sucursales
    sucursales_data = []
    for sucursal in sucursales:
        # Verificar si está abierta ahora
        abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(sucursal.id)
        
        # Obtener horarios para mostrar
        horarios_info = []
        for horario in sucursal.horarios:
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            if horario.cerrado:
                horarios_info.append(f"{dias[horario.dia_semana]}: Cerrado")
            else:
                horarios_info.append(f"{dias[horario.dia_semana]}: {horario.hora_apertura.strftime('%H:%M')} - {horario.hora_cierre.strftime('%H:%M')}")
        
        sucursales_data.append({
            'id': sucursal.id,
            'nombre': sucursal.nombre,
            'direccion': sucursal.direccion,
            'telefono': sucursal.telefono,
            'activa': sucursal.activa,
            'abierta_ahora': abierta_ahora,
            'horarios': horarios_info
        })
    
    productos = []
    total = 0
    for item in carrito:
        producto = MenuItem.query.get(int(item['producto_id']))
        if not producto:
            continue
        extras_objs = [Extra.query.get(int(eid)) for eid in item.get('extras', [])]
        cantidad = int(item.get('cantidad', 1))
        precio_base = float(producto.precio) * cantidad
        precio_extras = sum([e.precio for e in extras_objs if e]) * 1  # extras ya son por unidad histórica
        # Procesar opciones personalizadas (nueva estructura)
        opciones_info = []
        precio_opciones_total = 0.0
        for op in item.get('opciones_personalizadas', []):
            texto = op.get('valor_texto') or op.get('texto') or op.get('nombre') or op.get('opcion_titulo') or 'Opción'
            precio_op = op.get('precio')
            if precio_op is None:
                precio_op = op.get('valor_precio')
            try:
                precio_op = float(precio_op) if precio_op else 0.0
            except (TypeError, ValueError):
                precio_op = 0.0
            if precio_op > 0:
                opciones_info.append(f"{texto} (+${precio_op:.2f})")
                precio_opciones_total += precio_op * cantidad
            else:
                opciones_info.append(texto)
        subtotal = precio_base + precio_extras + precio_opciones_total
        productos.append({
            'producto': producto,
            'extras': extras_objs,
            'cantidad': cantidad,
            'subtotal': subtotal,
            'opciones_info': opciones_info
        })
        total += subtotal
    
    # Determinar template según dispositivo
    if is_mobile_device():
        template_name = 'checkout_mobile.html'
        print("📱 Sirviendo checkout móvil")
    else:
        template_name = 'checkout_desktop.html'
        print("💻 Sirviendo checkout escritorio")
    
    return render_template(template_name, productos=productos, total=total, sucursales=sucursales_data)

@app.route('/confirmacion')
def confirmacion():
    numero_pedido = session.get('ultimo_numero_pedido')
    sucursal_confirmada = session.pop('ultima_sucursal_pedido', None)
    
    # Detectar dispositivo y usar template apropiado
    if is_mobile_device():
        template_name = 'confirmacion_mobile.html'
        print("📱 Sirviendo confirmación móvil")
    else:
        template_name = 'confirmacion_desktop.html'
        print("💻 Sirviendo confirmación escritorio")
    
    return render_template(template_name, numero_pedido=numero_pedido, sucursal_confirmada=sucursal_confirmada)

@app.route('/consultar-pedido', methods=['GET', 'POST'])
def consultar_pedido():
    pedido = None
    error = None
    
    if request.method == 'POST':
        numero_pedido = request.form.get('numero_pedido', '').strip().upper()
        
        if numero_pedido:
            # Buscar pedido por número (simplificado)
            pedido = PedidoCliente.query.filter_by(numero_pedido=numero_pedido).first()
            
            if not pedido:
                error = "No se encontró ningún pedido con ese número. Verifica que el número de pedido sea correcto."
        else:
            error = "Por favor, ingresa el número de pedido."
    
    # Detectar dispositivo y usar template apropiado
    if is_mobile_device():
        template_name = 'consultar_pedido_mobile.html'
        print("📱 Sirviendo consultar pedido móvil")
    else:
        template_name = 'consultar_pedido_desktop.html'
        print("💻 Sirviendo consultar pedido escritorio")
    
    return render_template(template_name, pedido=pedido, error=error)

# API sucursales (para selector móvil)
@app.route('/api/sucursales')
def api_sucursales():
    sucursales = Sucursal.query.filter_by(activa=True).all()
    data = []
    for s in sucursales:
        try:
            abierta_ahora = HorarioSucursal.sucursal_abierta_ahora(s.id)
        except Exception:
            abierta_ahora = False
        data.append({
            'id': s.id,
            'nombre': s.nombre,
            'direccion': s.direccion,
            'telefono': s.telefono,
            'abierta_ahora': abierta_ahora
        })
    return jsonify({'sucursales': data})

@app.route('/api/pedido_estado')
def api_pedido_estado():
    """Devuelve estado actual de un pedido por numero ?numero=ABC12345"""
    numero = request.args.get('numero','').strip().upper()
    if not numero:
        return jsonify({'ok': False, 'error': 'Falta numero'}), 400
    pedido = PedidoCliente.query.filter_by(numero_pedido=numero).first()
    if not pedido:
        return jsonify({'ok': False, 'error': 'No encontrado'}), 404
    # Se podría añadir lógica de seguridad/token si se requiere
    return jsonify({
        'ok': True,
        'numero': pedido.numero_pedido,
        'estado': pedido.estado,
        'total': float(pedido.total or 0),
        'forma_pago': pedido.forma_pago,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/sse/pedido/<numero>')
def sse_pedido(numero):
    numero = (numero or '').upper()
    # Cabeceras para SSE
    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    }
    return Response(sse_stream(numero), headers=headers)

@app.route('/health')
def health():
    """Healthcheck básico y verificación de DB."""
    from sqlalchemy import text as _text
    status = {'ok': True}
    try:
        db.session.execute(_text('SELECT 1'))
        status['database'] = 'up'
    except Exception as e:
        status['ok'] = False
        status['database'] = f'down: {e.__class__.__name__}'
    return jsonify(status), (200 if status['ok'] else 500)

# ...importar modelos y rutas...

if __name__ == '__main__':
    # Nota: Render usará gunicorn, este bloque es solo para desarrollo local
    with app.app_context():
        db.create_all()
    debug_mode = os.getenv('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
