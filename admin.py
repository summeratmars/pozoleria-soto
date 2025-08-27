from flask import Blueprint, render_template, redirect, url_for, request, session, flash, current_app
from models import Sucursal, MenuItem, MenuItemSucursal, Extra, Administrador, Categoria, OpcionPersonalizada, ValorOpcion, HorarioSucursal, AdministradorSucursal, PedidoCliente
from extensions import db
import os
import re
from werkzeug.utils import secure_filename

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

ADMIN_USER = 'summeratmars'
ADMIN_PASS = 'Amoethan1'

def is_mobile_device():
    """Detecta si el dispositivo es móvil basándose en el User-Agent"""
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_patterns = [
        'mobile', 'android', 'iphone', 'ipad', 'ipod', 'blackberry', 
        'windows phone', 'opera mini', 'iemobile', 'wpdesktop'
    ]
    return any(pattern in user_agent for pattern in mobile_patterns)

def admin_responsive_template(base_name: str) -> str:
    """Devuelve el nombre de template admin (desktop/mobile) si existen variantes.
    Busca primero variante específica según dispositivo. Si no existe, cae al genérico.
    """
    # Rutas completas relativas dentro de templates
    mobile_candidate = f'admin/{base_name}_mobile.html'
    desktop_candidate = f'admin/{base_name}_desktop.html'
    generic = f'admin/{base_name}.html'
    templates_path = os.path.join(current_app.root_path, 'templates') if current_app else None
    def exists(rel):
        return templates_path and os.path.isfile(os.path.join(templates_path, rel.replace('/', os.sep)))
    mobile = is_mobile_device()
    if mobile and exists(mobile_candidate):
        return mobile_candidate
    if (not mobile) and exists(desktop_candidate):
        return desktop_candidate
    # Fallback preferencias: desktop, mobile, genérico
    if exists(desktop_candidate):
        return desktop_candidate
    if exists(mobile_candidate):
        return mobile_candidate
    return generic

ADMIN_USER = 'summeratmars'
ADMIN_PASS = 'Amoethan1'

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    from models import Administrador
    # Seed automático si la tabla está vacía
    try:
        if Administrador.query.count() == 0:
            import os
            seed_user = os.getenv('ADMIN_DEFAULT_USER', ADMIN_USER)
            seed_pass = os.getenv('ADMIN_DEFAULT_PASS', ADMIN_PASS)
            seed_nombre = os.getenv('ADMIN_DEFAULT_NOMBRE', 'Administrador')
            db.session.add(Administrador(usuario=seed_user, password=seed_pass, nombre=seed_nombre, rol='super'))
            db.session.commit()
            flash('Administrador inicial creado, ingresa con esas credenciales.', 'info')
    except Exception as e:
        db.session.rollback()
        print('[ADMIN][SEED] Error creando admin inicial:', e)
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        admin = Administrador.query.filter_by(usuario=user, password=pw).first()
        if admin:
            session['admin_logged_in'] = True
            session['admin_user'] = admin.usuario
            session['admin_nombre'] = admin.nombre  # <-- Guarda el nombre real
            session['admin_rol'] = admin.rol or 'empleado'
            # Cargar sucursales permitidas (IDs) salvo super
            if admin.rol == 'super':
                session['sucursales_permitidas'] = 'ALL'
            else:
                session['sucursales_permitidas'] = [s.id for s in admin.sucursales]
            return redirect(url_for('admin.dashboard'))
        flash('Credenciales incorrectas')
    # Render unificado
    return render_template(admin_responsive_template('login'))

@admin_bp.route('/logout')
@login_required
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_user', None)
    session.pop('admin_nombre', None)
    session.pop('admin_rol', None)
    session.pop('sucursales_permitidas', None)
    return redirect(url_for('admin.login'))

@admin_bp.route('/')
@login_required
def dashboard():
    from models import PedidoCliente
    from datetime import datetime, date
    from sqlalchemy import func
    
    # Datos básicos
    establecimientos = Sucursal.query.all()
    menu = MenuItem.query.all()
    total_admins = Administrador.query.count()
    
    # Estadísticas de pedidos
    hoy = date.today()
    total_pedidos_hoy = PedidoCliente.query.filter(
        func.date(PedidoCliente.fecha) == hoy
    ).count()
    
    # Ingresos del día
    ingresos_hoy = db.session.query(func.sum(PedidoCliente.total)).filter(
        func.date(PedidoCliente.fecha) == hoy
    ).scalar() or 0
    
    # Pedidos por estado
    pedidos_pendientes = PedidoCliente.query.filter_by(estado='Pendiente').count()
    pedidos_en_camino = PedidoCliente.query.filter_by(estado='En camino').count()
    pedidos_completados_hoy = PedidoCliente.query.filter(
        func.date(PedidoCliente.fecha) == hoy,
        PedidoCliente.estado == 'Entregado'
    ).count()
    
    # Pedidos recientes (últimos 5)
    pedidos_query = PedidoCliente.query.order_by(PedidoCliente.fecha.desc())
    sp = session.get('sucursales_permitidas')
    if sp and sp != 'ALL':
        pedidos_query = pedidos_query.filter(PedidoCliente.sucursal_id.in_(sp))
    pedidos_recientes = pedidos_query.limit(5).all()
    
    # Fecha y hora actual
    now = datetime.now()
    
    # Render unificado
    return render_template(admin_responsive_template('dashboard'), 
                         establecimientos=establecimientos, 
                         sucursales=establecimientos,  # Mantener compatibilidad con templates
                         menu=menu,
                         now=now,
                         total_admins=total_admins,
                         total_pedidos_hoy=total_pedidos_hoy,
                         ingresos_hoy=ingresos_hoy,
                         pedidos_pendientes=pedidos_pendientes,
                         pedidos_en_camino=pedidos_en_camino,
                         pedidos_completados_hoy=pedidos_completados_hoy,
                         pedidos_recientes=pedidos_recientes,
                         total_productos=len(menu),
                         total_categorias=Categoria.query.count(),
                         total_establecimientos=len(establecimientos),
                         total_sucursales=len(establecimientos),  # Mantener compatibilidad
                         establecimientos_stats=establecimientos,
                         sucursales_stats=establecimientos)  # Mantener compatibilidad

# CRUD Establecimientos
@admin_bp.route('/sucursales/nueva', methods=['GET', 'POST'])
@login_required
def nueva_sucursal():
    if request.method == 'POST':
        # Uso de get para evitar KeyError y validaciones básicas
        nombre = (request.form.get('nombre') or '').strip()
        direccion = (request.form.get('direccion') or '').strip()
        telefono = (request.form.get('telefono') or '').strip()
        if not nombre or not direccion or not telefono:
            flash('Todos los campos son obligatorios.', 'danger')
            return render_template(admin_responsive_template('nueva_sucursal'))
        # Nuevo establecimiento está activo por defecto
        activa = 'activa' in request.form if 'activa' in request.form else True
        nuevo_establecimiento = Sucursal(nombre=nombre, direccion=direccion, telefono=telefono, activa=activa)
        db.session.add(nuevo_establecimiento)
        db.session.commit()
        flash(f'Establecimiento "{nombre}" creado exitosamente.', 'success')
        return redirect(url_for('admin.listar_sucursales'))
    return render_template(admin_responsive_template('nueva_sucursal'))

@admin_bp.route('/sucursales')
@login_required
def listar_sucursales():
    from models import Sucursal
    establecimientos = Sucursal.query.all()
    
    # Calcular estadísticas
    establecimientos_activos = len([s for s in establecimientos if s.activa])
    establecimientos_inactivos = len([s for s in establecimientos if not s.activa])
    
    # Render unificado
    return render_template(admin_responsive_template('listar_sucursales'), 
                         establecimientos=establecimientos,
                         sucursales=establecimientos,  # Mantener compatibilidad con templates
                         establecimientos_activos=establecimientos_activos,
                         establecimientos_inactivos=establecimientos_inactivos,
                         sucursales_activas=establecimientos_activos,  # Mantener compatibilidad
                         sucursales_inactivas=establecimientos_inactivos)  # Mantener compatibilidad

@admin_bp.route('/sucursales/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_sucursal(id):
    establecimiento = Sucursal.query.get_or_404(id)
    if request.method == 'POST':
        establecimiento.nombre = request.form['nombre']
        establecimiento.direccion = request.form['direccion']
        establecimiento.telefono = request.form['telefono']
        # Manejar el campo activa (checkbox)
        establecimiento.activa = 'activa' in request.form
        db.session.commit()
        flash(f'Establecimiento "{establecimiento.nombre}" actualizado exitosamente.', 'success')
        return redirect(url_for('admin.listar_sucursales'))
    return render_template(admin_responsive_template('editar_sucursal'), sucursal=establecimiento, establecimiento=establecimiento)

@admin_bp.route('/sucursales/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_sucursal(id):
    establecimiento = Sucursal.query.get_or_404(id)
    
    # Verificar si el establecimiento tiene menús asociados
    if establecimiento.menuitems:
        flash(f'No se puede eliminar el establecimiento "{establecimiento.nombre}" porque tiene productos asociados. Elimine primero los productos.', 'danger')
        return redirect(url_for('admin.listar_sucursales'))
    
    # Verificar si hay pedidos asociados a este establecimiento
    from models import PedidoCliente
    pedidos = PedidoCliente.query.filter_by(sucursal_id=id).first()
    if pedidos:
        flash(f'No se puede eliminar el establecimiento "{establecimiento.nombre}" porque tiene pedidos asociados.', 'danger')
        return redirect(url_for('admin.listar_sucursales'))
    
    nombre_establecimiento = establecimiento.nombre
    try:
        db.session.delete(establecimiento)
        db.session.commit()
        flash(f'Establecimiento "{nombre_establecimiento}" eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el establecimiento: {str(e)}', 'danger')
    
    return redirect(url_for('admin.listar_sucursales'))

# CRUD Horarios de Establecimientos
@admin_bp.route('/sucursales/<int:sucursal_id>/horarios')
@login_required
def gestionar_horarios(sucursal_id):
    """Gestionar horarios de un establecimiento específico"""
    establecimiento = Sucursal.query.get_or_404(sucursal_id)
    establecimientos = Sucursal.query.all()  # Para el dropdown de copiar horarios
    
    # Obtener horarios existentes
    horarios_existentes = {h.dia_semana: h for h in establecimiento.horarios}
    
    # Crear lista completa de días con horarios existentes o vacíos
    dias_semana = HorarioSucursal.obtener_dias_semana()
    horarios_completos = []
    
    for dia_num, dia_nombre in dias_semana:
        if dia_num in horarios_existentes:
            horarios_completos.append(horarios_existentes[dia_num])
        else:
            # Placeholder cerrado (comportamiento clásico) para evitar mostrar día abierto sin horas
            horarios_completos.append(HorarioSucursal(
                sucursal_id=sucursal_id,
                dia_semana=dia_num,
                cerrado=True,
                hora_apertura=None,
                hora_cierre=None
            ))
    
    return render_template(admin_responsive_template('gestionar_horarios'), 
                         establecimiento=establecimiento,
                         sucursal=establecimiento,  # Mantener compatibilidad con template
                         establecimientos=establecimientos,
                         sucursales=establecimientos,  # Mantener compatibilidad con template
                         horarios=horarios_completos,
                         dias_semana=dias_semana)

@admin_bp.route('/sucursales/<int:sucursal_id>/horarios/guardar', methods=['POST'])
@login_required
def guardar_horarios(sucursal_id):
    """Guardar los horarios de un establecimiento"""
    from datetime import time
    
    establecimiento = Sucursal.query.get_or_404(sucursal_id)
    
    try:
        # Eliminar horarios existentes
        HorarioSucursal.query.filter_by(sucursal_id=sucursal_id).delete()
        
        # Procesar cada día de la semana
        for dia in range(7):  # 0-6 (Lunes a Domingo)
            cerrado = f'cerrado_{dia}' in request.form
            
            if cerrado:
                # Día cerrado
                horario = HorarioSucursal(
                    sucursal_id=sucursal_id,
                    dia_semana=dia,
                    cerrado=True,
                    hora_apertura=None,
                    hora_cierre=None
                )
            else:
                # Día abierto - obtener horarios
                hora_apertura_str = request.form.get(f'apertura_{dia}')
                hora_cierre_str = request.form.get(f'cierre_{dia}')
                
                if hora_apertura_str and hora_cierre_str:
                    try:
                        # Convertir strings a objetos time
                        hora_apertura = time.fromisoformat(hora_apertura_str)
                        hora_cierre = time.fromisoformat(hora_cierre_str)
                        
                        # Validar que la hora de cierre sea después de la apertura
                        if hora_cierre <= hora_apertura:
                            flash(f'Error: La hora de cierre debe ser posterior a la hora de apertura para el día {["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][dia]}.', 'danger')
                            return redirect(url_for('admin.gestionar_horarios', sucursal_id=sucursal_id))
                        
                        horario = HorarioSucursal(
                            sucursal_id=sucursal_id,
                            dia_semana=dia,
                            cerrado=False,
                            hora_apertura=hora_apertura,
                            hora_cierre=hora_cierre
                        )
                    except ValueError:
                        flash(f'Error: Formato de hora inválido para el día {["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][dia]}.', 'danger')
                        return redirect(url_for('admin.gestionar_horarios', sucursal_id=sucursal_id))
                else:
                    # Si no se especifican horarios, marcar como cerrado
                    horario = HorarioSucursal(
                        sucursal_id=sucursal_id,
                        dia_semana=dia,
                        cerrado=True,
                        hora_apertura=None,
                        hora_cierre=None
                    )
            
            db.session.add(horario)
        
        db.session.commit()
        flash(f'Horarios de la sucursal "{establecimiento.nombre}" guardados exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar horarios: {str(e)}', 'danger')
    
    # Regresar a la pantalla de gestión de horarios para que el admin confirme visualmente
    return redirect(url_for('admin.gestionar_horarios', sucursal_id=sucursal_id))

@admin_bp.route('/sucursales/<int:sucursal_id>/horarios/copiar', methods=['POST'])
@login_required
def copiar_horarios(sucursal_id):
    """Copiar horarios desde otra sucursal"""
    sucursal_origen_id = request.form.get('sucursal_origen_id')
    
    if not sucursal_origen_id:
        flash('Debe seleccionar una sucursal de origen.', 'danger')
        return redirect(url_for('admin.gestionar_horarios', sucursal_id=sucursal_id))
    
    try:
        sucursal_origen_id = int(sucursal_origen_id)
        sucursal_destino = Sucursal.query.get_or_404(sucursal_id)
        sucursal_origen = Sucursal.query.get_or_404(sucursal_origen_id)
        
        # Eliminar horarios existentes de la sucursal destino
        HorarioSucursal.query.filter_by(sucursal_id=sucursal_id).delete()
        
        # Copiar horarios de la sucursal origen
        for horario_origen in sucursal_origen.horarios:
            nuevo_horario = HorarioSucursal(
                sucursal_id=sucursal_id,
                dia_semana=horario_origen.dia_semana,
                hora_apertura=horario_origen.hora_apertura,
                hora_cierre=horario_origen.hora_cierre,
                cerrado=horario_origen.cerrado
            )
            db.session.add(nuevo_horario)
        
        db.session.commit()
        flash(f'Horarios copiados exitosamente desde "{sucursal_origen.nombre}" hacia "{sucursal_destino.nombre}".', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al copiar horarios: {str(e)}', 'danger')
    
    return redirect(url_for('admin.gestionar_horarios', sucursal_id=sucursal_id))

# CRUD Menú
@admin_bp.route('/menu/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_menuitem():
    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        precio = float(request.form['precio'])
        imagen_file = request.files.get('imagen')
        # Política: almacenar solo filename para imágenes subidas; si es URL externa (http/https) se guarda completa
        imagen_guardar = ""
        if imagen_file and imagen_file.filename:
            from werkzeug.utils import secure_filename
            import os
            filename = secure_filename(imagen_file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            imagen_file.save(filepath)
            imagen_guardar = filename  # solo filename
        else:
            posible_url = (request.form.get('imagen_url') or '').strip()
            if posible_url:
                if posible_url.startswith('http://') or posible_url.startswith('https://'):
                    imagen_guardar = posible_url
                else:
                    # Si el usuario pegó algo como /static/uploads/archivo.png lo normalizamos
                    if '/static/uploads/' in posible_url:
                        imagen_guardar = posible_url.split('/static/uploads/')[-1]
                    else:
                        imagen_guardar = posible_url  # asumir filename puro
        categoria_id = int(request.form['categoria_id'])
        item = MenuItem(
            nombre=nombre,
            descripcion=descripcion,
            precio=precio,
            imagen=imagen_guardar,
            categoria_id=categoria_id
        )
        db.session.add(item)
        db.session.flush()  # Para obtener el id del item antes de commit

        # Guardar disponibilidad por sucursal
        for s in Sucursal.query.all():
            disponible = request.form.get(f'disponible_{s.id}') == 'on'
            db.session.add(MenuItemSucursal(menuitem_id=item.id, sucursal_id=s.id, disponible=disponible))
        
        # Guardar opciones personalizadas
        opciones = request.form.getlist('opcion_titulo')
        tipos = request.form.getlist('opcion_tipo')
        valores = request.form.getlist('opcion_valores')
        
        for idx, titulo in enumerate(opciones):
            if titulo.strip():
                # Verificar si esta opción específica está marcada como obligatoria
                obligatorio_key = f'opcion_obligatorio_{idx}'
                es_obligatorio = request.form.get(obligatorio_key) == 'on'
                
                op = OpcionPersonalizada(
                    menuitem_id=item.id,
                    titulo=titulo,
                    obligatorio=es_obligatorio,
                    tipo=tipos[idx] if idx < len(tipos) else 'radio'
                )
                db.session.add(op)
                db.session.flush()
                
                # Procesar valores separados por salto de línea
                if idx < len(valores):
                    for val_line in valores[idx].split('\n'):
                        val_line = val_line.strip()
                        if val_line:
                            # Si el valor tiene precio, formato: texto|precio
                            if '|' in val_line:
                                parts = val_line.split('|', 1)
                                texto = parts[0].strip()
                                try:
                                    precio = float(parts[1].strip()) if parts[1].strip() else 0
                                except ValueError:
                                    precio = 0
                                db.session.add(ValorOpcion(opcion_id=op.id, texto=texto, precio=precio))
                            else:
                                # Sin precio especificado, precio = 0
                                db.session.add(ValorOpcion(opcion_id=op.id, texto=val_line, precio=0))
        db.session.commit()
        return redirect(url_for('admin.listar_menu'))
    establecimientos = Sucursal.query.all()
    categorias = Categoria.query.all()
    return render_template(admin_responsive_template('nuevo_menuitem'), 
                         establecimientos=establecimientos, 
                         sucursales=establecimientos,  # Mantener compatibilidad
                         categorias=categorias)

@admin_bp.route('/menu')
@login_required
def listar_menu():
    from models import MenuItem, Categoria
    menu = MenuItem.query.all()
    categorias = Categoria.query.all()
    
    # Calcular estadísticas basadas en disponibilidad en al menos una sucursal
    productos_disponibles = 0
    productos_no_disponibles = 0
    
    for item in menu:
        # Un producto está disponible si está disponible en al menos una sucursal
        disponible_en_alguna_sucursal = any(rel.disponible for rel in item.sucursales)
        # Exponer atributo dinámico para la plantilla (si no existe en el modelo Jinja lo ve como falso)
        try:
            setattr(item, 'disponible', disponible_en_alguna_sucursal)
            # Asegurar atributo "opciones_personalizadas" para que las plantillas existentes muestren el conteo correcto
            if not hasattr(item, 'opciones_personalizadas'):
                setattr(item, 'opciones_personalizadas', item.opciones)
        except Exception:
            pass
        if disponible_en_alguna_sucursal:
            productos_disponibles += 1
        else:
            productos_no_disponibles += 1
    
    # Render unificado
    return render_template(admin_responsive_template('listar_menu'), 
                         menu_items=menu, 
                         categorias=categorias,
                         productos_disponibles=productos_disponibles,
                         productos_no_disponibles=productos_no_disponibles)

@admin_bp.route('/menu/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_menuitem(id):
    item = MenuItem.query.get_or_404(id)
    sucursales = Sucursal.query.all()
    categorias = Categoria.query.all()
    if request.method == 'POST':
        item.nombre = request.form['nombre']
        item.descripcion = request.form['descripcion']
        item.precio = float(request.form['precio'])
        imagen_file = request.files.get('imagen')
        if imagen_file and imagen_file.filename:
            from werkzeug.utils import secure_filename
            import os
            filename = secure_filename(imagen_file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            imagen_file.save(filepath)
            item.imagen = filename  # solo filename
        else:
            imagen_url = (request.form.get('imagen_url') or '').strip()
            if imagen_url:
                if imagen_url.startswith('http://') or imagen_url.startswith('https://'):
                    item.imagen = imagen_url
                else:
                    if '/static/uploads/' in imagen_url:
                        item.imagen = imagen_url.split('/static/uploads/')[-1]
                    else:
                        item.imagen = imagen_url  # filename
        item.categoria_id = int(request.form['categoria_id'])
        # Opciones personalizadas
        # Elimina todas las opciones y valores previos
        for op in item.opciones:
            for val in op.valores:
                db.session.delete(val)
            db.session.delete(op)
        db.session.flush()
        # Crea nuevas opciones y valores
        opciones = request.form.getlist('opcion_titulo')
        tipos = request.form.getlist('opcion_tipo')
        valores = request.form.getlist('opcion_valores')
        for idx, titulo in enumerate(opciones):
            if titulo.strip():
                # Verificar si esta opción específica está marcada como obligatoria
                obligatorio_key = f'opcion_obligatorio_{idx}'
                es_obligatorio = request.form.get(obligatorio_key) == 'on'
                
                op = OpcionPersonalizada(
                    menuitem_id=item.id,
                    titulo=titulo,
                    obligatorio=es_obligatorio,
                    tipo=tipos[idx] if idx < len(tipos) else 'radio'
                )
                db.session.add(op)
                db.session.flush()
                # Procesar valores separados por salto de línea
                for val_line in valores[idx].split('\n'):
                    val_line = val_line.strip()
                    if val_line:
                        # Si el valor tiene precio, formato: texto|precio
                        if '|' in val_line:
                            parts = val_line.split('|', 1)
                            texto = parts[0].strip()
                            try:
                                precio = float(parts[1].strip()) if parts[1].strip() else 0
                            except ValueError:
                                precio = 0
                            db.session.add(ValorOpcion(opcion_id=op.id, texto=texto, precio=precio))
                        else:
                            # Sin precio especificado, precio = 0
                            db.session.add(ValorOpcion(opcion_id=op.id, texto=val_line, precio=0))
        
        # Actualizar disponibilidad por sucursal
        for s in sucursales:
            # Buscar la relación existente
            rel_existente = MenuItemSucursal.query.filter_by(menuitem_id=item.id, sucursal_id=s.id).first()
            disponible = request.form.get(f'disponible_{s.id}') == 'on'
            
            if rel_existente:
                # Actualizar la relación existente
                rel_existente.disponible = disponible
            else:
                # Crear nueva relación si no existe
                db.session.add(MenuItemSucursal(menuitem_id=item.id, sucursal_id=s.id, disponible=disponible))
        
        db.session.commit()
        return redirect(url_for('admin.listar_menu'))
    # Obtener disponibilidad actual
    disponibilidad = {}
    for s in sucursales:
        rel = MenuItemSucursal.query.filter_by(menuitem_id=item.id, sucursal_id=s.id).first()
        disponibilidad[s.id] = rel.disponible if rel else False
    return render_template(admin_responsive_template('editar_menuitem'), item=item, sucursales=sucursales, categorias=categorias, disponibilidad=disponibilidad)

@admin_bp.route('/menu/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_menuitem(id):
    item = MenuItem.query.get_or_404(id)
    nombre_item = item.nombre
    
    try:
        # Eliminar opciones personalizadas y sus valores
        for op in item.opciones:
            for val in op.valores:
                db.session.delete(val)
            db.session.delete(op)
        
        # Eliminar relaciones con sucursales
        for rel in item.sucursales:
            db.session.delete(rel)
        
        # Eliminar el producto
        db.session.delete(item)
        db.session.commit()
        
        flash(f'Producto "{nombre_item}" eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar el producto: {str(e)}', 'danger')
    
    return redirect(url_for('admin.listar_menu'))

# CRUD Administradores
@admin_bp.route('/administradores')
@login_required
def listar_administradores():
    admins = Administrador.query.all()
    return render_template(admin_responsive_template('listar_administradores'), admins=admins)

@admin_bp.route('/administradores/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_administrador():
    sucursales = Sucursal.query.all()
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']
        nombre = request.form['nombre']
        rol = request.form.get('rol', 'empleado')
        admin = Administrador(usuario=usuario, password=password, nombre=nombre, rol=rol)
        db.session.add(admin)
        db.session.flush()
        # Asignar sucursales si no es super
        if rol != 'super':
            suc_ids = request.form.getlist('sucursales_ids')
            for sid in suc_ids:
                try:
                    db.session.add(AdministradorSucursal(administrador_id=admin.id, sucursal_id=int(sid)))
                except ValueError:
                    continue
        db.session.commit()
        return redirect(url_for('admin.listar_administradores'))
    return render_template(admin_responsive_template('nuevo_administrador'), sucursales=sucursales)

@admin_bp.route('/administradores/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_administrador(id):
    admin = Administrador.query.get_or_404(id)
    sucursales = Sucursal.query.all()
    if request.method == 'POST':
        admin.usuario = request.form['usuario']
        admin.password = request.form['password']
        admin.nombre = request.form['nombre']
        admin.rol = request.form.get('rol', admin.rol or 'empleado')
        # Limpiar asignaciones previas si no es super
        if admin.rol != 'super':
            AdministradorSucursal.query.filter_by(administrador_id=admin.id).delete()
            for sid in request.form.getlist('sucursales_ids'):
                try:
                    db.session.add(AdministradorSucursal(administrador_id=admin.id, sucursal_id=int(sid)))
                except ValueError:
                    continue
        else:
            # Si es super, eliminar asignaciones específicas (tiene acceso total)
            AdministradorSucursal.query.filter_by(administrador_id=admin.id).delete()
        db.session.commit()
        return redirect(url_for('admin.listar_administradores'))
    # IDs actuales
    sucursales_asignadas = {rel.sucursal_id for rel in AdministradorSucursal.query.filter_by(administrador_id=admin.id).all()}
    return render_template(admin_responsive_template('editar_administrador'), admin=admin, sucursales=sucursales, sucursales_asignadas=sucursales_asignadas)

# Elimina o comenta la ruta de pedidos que no quieres mostrar
# @admin_bp.route('/pedidos')
# @login_required
# def listar_pedidos():
#     from models import Pedido, Sucursal
#     pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
#     sucursales = {s.id: s.nombre for s in Sucursal.query.all()}
#     return render_template('admin/listar_pedidos.html', pedidos=pedidos, sucursales=sucursales)

@admin_bp.route('/pedidos/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_pedido():
    from models import Sucursal, MenuItem, Pedido
    sucursales = Sucursal.query.all()
    productos = MenuItem.query.all()
    if request.method == 'POST':
        cliente = request.form['cliente']
        fecha = request.form['fecha']
        sucursal_id = int(request.form['sucursal_id'])
        productos_seleccionados = request.form.getlist('productos')
        total = float(request.form['total'])
        productos_str = ', '.join(productos_seleccionados)
        db.session.add(Pedido(cliente=cliente, fecha=fecha, sucursal_id=sucursal_id, productos=productos_str, total=total))
        db.session.commit()
        return redirect(url_for('admin.listar_pedidos'))
    return render_template(admin_responsive_template('nuevo_pedido'), sucursales=sucursales, productos=productos)

@admin_bp.route('/pedidos_clientes')
@login_required
def listar_pedidos_clientes():
    from models import PedidoCliente, Sucursal
    sp = session.get('sucursales_permitidas')
    base = PedidoCliente.query.order_by(PedidoCliente.fecha.desc())
    if sp and sp != 'ALL':
        base = base.filter(PedidoCliente.sucursal_id.in_(sp))
    pedidos = base.all()
    # Limitar sucursales mostradas
    if sp == 'ALL' or not sp:
        sucursales = Sucursal.query.all()
    else:
        sucursales = Sucursal.query.filter(Sucursal.id.in_(sp)).all()
    
    # Calcular estadísticas
    pedidos_pendientes = len([p for p in pedidos if p.estado == 'pendiente'])
    pedidos_completados = len([p for p in pedidos if p.estado == 'entregado'])
    
    # Render unificado
    return render_template(admin_responsive_template('listar_pedidos_clientes'), 
                         pedidos=pedidos, 
                         sucursales=sucursales,
                         pedidos_pendientes=pedidos_pendientes,
                         pedidos_completados=pedidos_completados)

@admin_bp.route('/pedidos_clientes/<int:id>')
@login_required
def ver_pedido_cliente(id):
    from models import PedidoCliente
    pedido = PedidoCliente.query.get_or_404(id)
    sp = session.get('sucursales_permitidas')
    if sp and sp != 'ALL' and pedido.sucursal_id not in sp:
        flash('No tienes permiso para ver este pedido.', 'danger')
        return redirect(url_for('admin.listar_pedidos_clientes'))
    
    # Detectar dispositivo y usar template apropiado
    from app import is_mobile_device
    if is_mobile_device():
        template_name = 'pedido_cliente_mobile.html'
        print("📱 Sirviendo pedido cliente móvil")
    else:
        template_name = 'pedido_cliente_desktop.html'
        print("💻 Sirviendo pedido cliente escritorio")
    
    return render_template(template_name, pedido=pedido)

@admin_bp.route('/pedidos_clientes/actualizar/<int:id>', methods=['POST'])
@login_required
def actualizar_estado_pedido(id):
    from models import PedidoCliente
    pedido = PedidoCliente.query.get_or_404(id)
    sp = session.get('sucursales_permitidas')
    if sp and sp != 'ALL' and pedido.sucursal_id not in sp:
        flash('No tienes permiso para modificar este pedido.', 'danger')
        return redirect(url_for('admin.listar_pedidos_clientes'))
    pedido.estado = request.form['estado']
    db.session.commit()
    return redirect(url_for('admin.listar_pedidos_clientes'))

# CRUD Categorías
@admin_bp.route('/categorias')
@login_required
def listar_categorias():
    from models import Categoria, MenuItem
    categorias = Categoria.query.all()
    
    # Calcular estadísticas
    total_productos = MenuItem.query.count()
    
    # Render unificado
    return render_template(admin_responsive_template('listar_categorias'), 
                         categorias=categorias,
                         total_productos=total_productos)

@admin_bp.route('/categorias/nueva', methods=['GET', 'POST'])
@login_required
def nueva_categoria():
    from models import Categoria
    mensaje = None
    if request.method == 'POST':
        nombre = request.form['nombre']
        existente = Categoria.query.filter_by(nombre=nombre).first()
        if existente:
            mensaje = "La categoría ya existe."
        else:
            db.session.add(Categoria(nombre=nombre))
            db.session.commit()
            return redirect(url_for('admin.listar_categorias'))
    return render_template(admin_responsive_template('nueva_categoria'), mensaje=mensaje)

@admin_bp.route('/categorias/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_categoria(id):
    categoria = Categoria.query.get_or_404(id)
    if request.method == 'POST':
        categoria.nombre = request.form['nombre']
        db.session.commit()
        return redirect(url_for('admin.listar_categorias'))
    return render_template(admin_responsive_template('editar_categoria'), categoria=categoria)

@admin_bp.route('/categorias/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_categoria(id):
    categoria = Categoria.query.get_or_404(id)
    
    # Verificar que la categoría no tenga productos asociados
    if categoria.productos:
        flash(f'No se puede eliminar la categoría "{categoria.nombre}" porque tiene {len(categoria.productos)} productos asociados.', 'error')
        return redirect(url_for('admin.editar_categoria', id=id))
    
    # Eliminar la categoría
    nombre_categoria = categoria.nombre
    db.session.delete(categoria)
    db.session.commit()
    
    flash(f'La categoría "{nombre_categoria}" ha sido eliminada exitosamente.', 'success')
    return redirect(url_for('admin.listar_categorias'))
