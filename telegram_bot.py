import requests
import json
from datetime import datetime
from typing import Optional
import threading
import time
import os

# Configuración del bot de Telegram cargada desde variables de entorno
# (Nunca dejar tokens sensibles en el repositorio)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
ADMIN_CHAT_ID = os.getenv('TELEGRAM_ADMIN_CHAT_ID', '')
ALLOWED_CHATS = {c for c in {ADMIN_CHAT_ID} if c}

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ''

ESTADOS_MAP = {
    'pendiente': 'Pendiente',
    'pend': 'Pendiente',
    'p': 'Pendiente',
    'preparacion': 'En preparación',
    'preparación': 'En preparación',
    'prep': 'En preparación',
    'en_preparacion': 'En preparación',
    'en_preparación': 'En preparación',
    'en_camino': 'En camino',
    'encamino': 'En camino',
    'camino': 'En camino',
    'en': 'En camino',
    'c': 'En camino',
    'entregado': 'Entregado',
    'done': 'Entregado',
    'ok': 'Entregado',
    'e': 'Entregado',
    'cancelado': 'Cancelado',
    'canc': 'Cancelado',
    'x': 'Cancelado'
}

_POLL_OFFSET_FILE = 'telegram_offset.txt'
_polling_thread = None
_polling_running = False

def iniciar_polling_background(app=None, intervalo: int = 2):
    """Inicia un hilo en segundo plano para hacer polling si no hay webhook.

    Usar solo en desarrollo local (sin URL pública). Evita duplicados verificando variable global.
    """
    global _polling_thread, _polling_running
    if _polling_running:
        return
    # Evitar doble arranque por el reloader de Flask en debug
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not os.environ.get('FLASK_ENV'):
        _polling_running = True

        def _loop():
            while _polling_running:
                try:
                    # Asegurar contexto de aplicación si se pasó.
                    if app is not None:
                        with app.app_context():
                            poll_once()
                    else:
                        poll_once()
                except Exception as e:
                    print('[TELEGRAM] Error en loop polling:', e)
                time.sleep(intervalo)
        _polling_thread = threading.Thread(target=_loop, name='TelegramPolling', daemon=True)
        _polling_thread.start()

def poll_once():
    """Realiza una iteración de getUpdates para entornos sin webhook (desarrollo)."""
    if not TELEGRAM_TOKEN or not API_URL:
        print('[TELEGRAM] Token no configurado, no se enviará notificación.')
        return False
    try:
        offset = 0
        import os
        if os.path.isfile(_POLL_OFFSET_FILE):
            try:
                with open(_POLL_OFFSET_FILE, 'r', encoding='utf-8') as f:
                    offset = int(f.read().strip() or 0)
            except Exception:
                offset = 0
        r = requests.get(f"{API_URL}/getUpdates", params={'timeout': 0, 'offset': offset + 1}, timeout=10)
        data = r.json()
        if not data.get('ok'):
            print('[TELEGRAM] getUpdates fallo', data)
            return {'ok': False, 'error': data}
        updates = data.get('result', [])
        max_update_id = offset
        for upd in updates:
            procesar_update(upd)
            uid = upd.get('update_id', 0)
            if uid > max_update_id:
                max_update_id = uid
        if max_update_id != offset:
            with open(_POLL_OFFSET_FILE, 'w', encoding='utf-8') as f:
                f.write(str(max_update_id))
        return {'ok': True, 'nuevos': len(updates)}
    except Exception as e:
        print('[TELEGRAM] Error poll_once:', e)
        return {'ok': False, 'error': str(e)}

def _build_inline_keyboard(numero_pedido: str, estado_actual: str):
    """Construye teclado inline con estados disponibles (desactiva el actual)."""
    estados = ['Pendiente', 'En preparación', 'En camino', 'Entregado', 'Cancelado']
    buttons = []
    for est in estados:
        if est == estado_actual:
            # Botón 'activo' (sin callback)
            buttons.append({"text": f"✅ {est}", "callback_data": f"noop|{numero_pedido}"})
        else:
            est_code = est.lower().replace(' ', '_')
            buttons.append({"text": est, "callback_data": f"update_status|{numero_pedido}|{est_code}"})
    # Agrupar en una sola fila por simplicidad
    return {"inline_keyboard": [buttons]}

def _send(api_method: str, payload: dict):
    if not TELEGRAM_TOKEN or not API_URL:
        print('[TELEGRAM] Token no configurado, no se puede probar bot.')
        return False
    try:
        r = requests.post(f"{API_URL}/{api_method}", json=payload, timeout=10)
        if r.status_code != 200:
            print('[TELEGRAM] Error:', r.status_code, r.text)
        return r.json() if r.content else {}
    except Exception as e:
        print('[TELEGRAM] Excepción enviando:', e)
        return {}

def enviar_notificacion_pedido(pedido):
    """
    Envía una notificación al admin cuando se crea un nuevo pedido
    """
    if not TELEGRAM_TOKEN or not API_URL:
        print('[TELEGRAM] Token no configurado, ignorando update.')
        return
    try:
        # Formatear información del pedido
        fecha_formateada = pedido.fecha.strftime('%d/%m/%Y %H:%M') if pedido.fecha else 'No disponible'
        
        # Procesar productos desde JSON
        productos_texto = ""
        try:
            productos_lista = json.loads(pedido.productos) if pedido.productos else []
            for producto in productos_lista:
                productos_texto += f"• {producto.get('nombre', 'Producto')} x{producto.get('cantidad', 1)}"
                if producto.get('opciones_personalizadas'):
                    productos_texto += f" ({', '.join(producto['opciones_personalizadas'])})"
                productos_texto += f" - ${producto.get('precio_total', 0):.2f}\n"
        except (json.JSONDecodeError, TypeError):
            productos_texto = f"• {pedido.productos}\n"
        
        # Construir mensaje completo con helper reutilizable
        mensaje = build_pedido_message(pedido, productos_texto=productos_texto, fecha_formateada=fecha_formateada)

        # Enviar mensaje
        reply_markup = _build_inline_keyboard(pedido.numero_pedido, 'Pendiente')
        payload = {
            "chat_id": ADMIN_CHAT_ID,
            "text": mensaje,
            "parse_mode": "Markdown",
            "reply_markup": reply_markup
        }
        resp = _send('sendMessage', payload)
        ok = bool(resp.get('ok')) if isinstance(resp, dict) else False
        if ok:
            print(f"✅ Notificación de Telegram enviada exitosamente para pedido {pedido.numero_pedido}")
        else:
            print(f"❌ Error al enviar notificación de Telegram: {resp}")
        return ok
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión al enviar notificación de Telegram: {e}")
        return False
    except Exception as e:
        print(f"❌ Error inesperado al enviar notificación de Telegram: {e}")
        return False

def enviar_confirmacion(pedido):
    """
    Función de compatibilidad con el código anterior
    """
    return enviar_notificacion_pedido(pedido)

def test_telegram_bot():
    """
    Función para probar la conexión del bot
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            bot_info = response.json()
            print(f"✅ Bot conectado: {bot_info['result']['first_name']} (@{bot_info['result']['username']})")
            return True
        else:
            print(f"❌ Error al conectar con el bot: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error al probar el bot: {e}")
        return False

def procesar_update(update: dict):
    """Procesa un update entrante de Telegram (webhook)."""
    try:
        if 'message' in update:
            message = update['message']
            chat_id = str(message.get('chat', {}).get('id'))
            text = (message.get('text') or '').strip()
            if chat_id not in ALLOWED_CHATS:
                return
            if text.startswith('/'):
                manejar_comando(chat_id, text)
        elif 'callback_query' in update:
            cq = update['callback_query']
            chat_id = str(cq.get('message', {}).get('chat', {}).get('id'))
            data = cq.get('data', '')
            message_id = cq.get('message', {}).get('message_id')
            if chat_id not in ALLOWED_CHATS:
                return
            manejar_callback(chat_id, message_id, data, cq.get('id'))
    except Exception as e:
        print('[TELEGRAM] Error procesando update:', e)

def manejar_comando(chat_id: str, text: str):
    parts = text.split()
    cmd = parts[0].lower()
    if cmd == '/start':
        _send('sendMessage', {"chat_id": chat_id, "text": "Bot de pedidos activo. Usa /estado <NUMERO> <estado> o presiona botones en los pedidos."})
    elif cmd == '/estado' and len(parts) >= 3:
        numero = parts[1].strip().upper()
        estado_code = parts[2].lower()
        estado_destino = ESTADOS_MAP.get(estado_code)
        if not estado_destino:
            _send('sendMessage', {"chat_id": chat_id, "text": "Estado inválido. Usa: pendiente, en_camino, entregado"})
            return
        actualizar_estado_pedido_telegram(chat_id, numero, estado_destino)
    else:
        _send('sendMessage', {"chat_id": chat_id, "text": "Comando no reconocido."})

def manejar_callback(chat_id: str, message_id: int, data: str, callback_id: Optional[str]):
    try:
        print('[TELEGRAM] Callback recibido:', data)
        if data.startswith('update_status'):
            _, numero, estado_code = data.split('|', 2)
            estado_destino = ESTADOS_MAP.get(estado_code)
            if not estado_destino:
                return
            actualizar_estado_pedido_telegram(chat_id, numero, estado_destino, message_id=message_id, edit_original=True)
            # Enviar confirmación explícita en el chat
            _send('sendMessage', {
                'chat_id': chat_id,
                'text': f"PEDIDO {numero} ACTUALIZADO A: {estado_destino.upper()}"
            })
            # Popup (toast) de Telegram para feedback inmediato
            if callback_id:
                _send('answerCallbackQuery', {
                    "callback_query_id": callback_id,
                    "text": f"Estado -> {estado_destino}",
                    "show_alert": False
                })
        elif data.startswith('noop') and callback_id:
            _send('answerCallbackQuery', {"callback_query_id": callback_id, "text": "Estado actual"})
    except Exception as e:
        print('[TELEGRAM] Error en callback:', e)

def actualizar_estado_pedido_telegram(chat_id: str, numero_pedido: str, nuevo_estado: str, message_id: Optional[int]=None, edit_original: bool=False):
    """Actualiza el estado del pedido en DB y refleja en Telegram."""
    try:
        from extensions import db
        from models import PedidoCliente
        pedido = PedidoCliente.query.filter_by(numero_pedido=numero_pedido).first()
        if not pedido:
            _send('sendMessage', {"chat_id": chat_id, "text": f"Pedido {numero_pedido} no encontrado."})
            return
        pedido.estado = nuevo_estado
        db.session.commit()
        print(f'[TELEGRAM] Pedido {numero_pedido} -> {nuevo_estado}')
        # Broadcast SSE
        try:
            from event_bus import broadcast_pedido_estado
            broadcast_pedido_estado(numero_pedido, nuevo_estado)
        except Exception as be:
            print('[TELEGRAM] Broadcast SSE fallo:', be)
        if edit_original and message_id:
            # Re-editar el mensaje completo con todos los detalles + estado actualizado
            try:
                # Reusar parseo de productos
                fecha_formateada = pedido.fecha.strftime('%d/%m/%Y %H:%M') if pedido.fecha else 'No disponible'
                productos_texto = ""
                try:
                    productos_lista = json.loads(pedido.productos) if pedido.productos else []
                    for producto in productos_lista:
                        linea = f"• {producto.get('nombre','Producto')} x{producto.get('cantidad',1)}"
                        # Opciones/complementos
                        ops = producto.get('opciones_personalizadas') or []
                        if ops:
                            linea += " (" + ', '.join(ops) + ")"
                        # Precio total del item
                        linea += f" - ${producto.get('precio_total',0):.2f}\n"
                        productos_texto += linea
                except Exception:
                    productos_texto = f"• {pedido.productos}\n"
                mensaje_edit = build_pedido_message(pedido, estado_override=nuevo_estado, productos_texto=productos_texto, fecha_formateada=fecha_formateada)
            except Exception as ie:
                print('[TELEGRAM] Error reconstruyendo mensaje:', ie)
                mensaje_edit = f"PEDIDO {numero_pedido} ACTUALIZADO A: {nuevo_estado.upper()}"
            reply_markup = _build_inline_keyboard(numero_pedido, nuevo_estado)
            _send('editMessageText', {
                'chat_id': chat_id,
                'message_id': message_id,
                'text': mensaje_edit,
                'parse_mode': 'Markdown'
            })
            _send('editMessageReplyMarkup', {
                'chat_id': chat_id,
                'message_id': message_id,
                'reply_markup': reply_markup
            })
        else:
            # No tenemos message_id (comando /estado): enviar mensaje separado resumen
            texto = f"PEDIDO {numero_pedido} ACTUALIZADO A: {nuevo_estado.upper()}"
            _send('sendMessage', {'chat_id': chat_id, 'text': texto})
    except Exception as e:
        print('[TELEGRAM] Error actualizando estado:', e)
        # Recuperar estado actual si existe
        try:
            from models import PedidoCliente
            from extensions import db
            pedido = PedidoCliente.query.filter_by(numero_pedido=numero_pedido).first()
            estado_actual = pedido.estado if pedido else 'DESCONOCIDO'
        except Exception:
            estado_actual = 'DESCONOCIDO'
        _send('sendMessage', {"chat_id": chat_id, "text": f"ERROR AL ACTUALIZAR PEDIDO {numero_pedido} ESTADO ACTUAL: {estado_actual}"})

def build_pedido_message(pedido, *, estado_override: Optional[str]=None, productos_texto: Optional[str]=None, fecha_formateada: Optional[str]=None):
    """Genera el texto completo del pedido con todos los detalles para Telegram."""
    try:
        fecha_formateada = fecha_formateada or (pedido.fecha.strftime('%d/%m/%Y %H:%M') if getattr(pedido, 'fecha', None) else 'No disponible')
        # Reconstruir detalle productos de forma enumerada siempre para mayor claridad
        detalle_formateado = ''
        total_items = 0
        # Si ya nos pasaron un texto listo de productos (compatibilidad), úsalo directamente
        if productos_texto:
            detalle_formateado = productos_texto if productos_texto.endswith('\n') else productos_texto + '\n'
        else:
            detalle_formateado = ''

        def _emoji_producto(nombre: str):
            n = (nombre or '').lower()
            # Mapeo básico por palabras clave
            if 'pozole' in n or 'menudo' in n:
                return '🍲'
            if 'taco' in n:
                return '🌮'
            if 'tostada' in n:
                return '\U0001fad3'  # flatbread (tostada)
            if 'quesa' in n or 'queso' in n:
                return '🧀'
            if 'bebida' in n or 'refresco' in n or 'coca' in n or 'soda' in n:
                return '🥤'
            if 'agua' in n or 'horchata' in n or 'jamaica' in n or 'limonada' in n:
                return '💧'
            if 'postre' in n or 'flan' in n or 'pastel' in n:
                return '🍮'
            if 'carne' in n or 'res' in n or 'pollo' in n or 'cerdo' in n:
                return '🍖'
            return '🍽️'

        if not productos_texto:  # Solo reconstruir si no vino preformateado
            try:
                productos_raw = pedido.productos
                productos_lista = json.loads(productos_raw) if productos_raw else []
                if isinstance(productos_lista, list):
                    if not productos_lista:
                        print('[TELEGRAM] Debug: productos_lista vacío. Raw=', productos_raw)
                    for idx, producto in enumerate(productos_lista, start=1):
                        if not isinstance(producto, dict):
                            print('[TELEGRAM] Debug: elemento productos_lista no dict:', producto)
                            continue
                        nombre = producto.get('nombre', 'Producto')
                        cantidad = int(producto.get('cantidad', 1) or 1)
                        total_items += cantidad
                        precio_total_item = float(producto.get('precio_total', 0) or 0)
                        opciones = producto.get('opciones_personalizadas') or []
                        emoji = _emoji_producto(nombre)
                        detalle_formateado += f"{idx}) {emoji} {nombre} x{cantidad}  -  ${precio_total_item:.2f}\n"
                        for op in opciones:
                            if isinstance(op, dict):
                                texto_op = op.get('valor_texto') or op.get('texto') or op.get('nombre') or 'Opción'
                                precio_op = op.get('precio')
                                try:
                                    precio_op = float(precio_op) if precio_op not in (None, '', False) else 0.0
                                except (TypeError, ValueError):
                                    precio_op = 0.0
                                if precio_op > 0:
                                    texto_op += f" (+${precio_op:.2f})"
                                detalle_formateado += f"   • ➕ {texto_op}\n"
                            else:
                                detalle_formateado += f"   • ➕ {op}\n"
                    if not detalle_formateado:
                        if productos_lista:  # Lista no vacía pero sin dicts válidos
                            detalle_formateado = 'Formato de productos no reconocido\n'
                        else:
                            detalle_formateado = 'Sin productos registrados (lista vacía)\n'
                else:
                    # Estructura alternativa (string/dict)
                    if productos_raw:
                        detalle_formateado = f"• {productos_raw}\n"
                    else:
                        detalle_formateado = 'Sin productos registrados\n'
            except Exception:
                if pedido.productos:
                    detalle_formateado = f"• {pedido.productos}\n"
                else:
                    detalle_formateado = 'Sin productos registrados (error parse)\n'

            productos_texto = detalle_formateado
        else:
            productos_texto = detalle_formateado

        estado_actual = estado_override or pedido.estado or 'Pendiente'
        pago_line_extra = ''
        if pedido.forma_pago == 'transferencia':
            pago_line_extra = f"\n{ '🏦 **Transferencia:** ' + ('✅ Confirmada' if pedido.comprobante_transferencia else '⏳ Pendiente comprobante') }"
        cambio_line = f"\n💵 **Cambio para:** ${pedido.cambio_para:.2f}" if getattr(pedido, 'cambio_para', None) else ''
        mensaje = f"""🍲 **PEDIDO - POZOLERÍA SOTO**

📋 **Pedido #:** `{pedido.numero_pedido}`
🟢 **Estado:** {estado_actual}
👤 **Cliente:** {pedido.nombre}
📞 **Teléfono:** [{pedido.telefono}](tel:{pedido.telefono})

📍 **Dirección resumida:** {pedido.calle} #{pedido.numero}, {pedido.colonia}
🛣️ **Entre:** {pedido.entre_calles}
📝 **Ref:** {pedido.referencia}

🛒 **Detalle (total ítems: {total_items})**:
{productos_texto}💰 **TOTAL:** ${pedido.total:.2f}

💳 **Pago:** {pedido.forma_pago.title()}{cambio_line}{pago_line_extra}
🕐 **Hora:** {fecha_formateada}
🏪 **Sucursal:** {pedido.sucursal_id}
"""
        return mensaje
    except Exception as e:
        print('[TELEGRAM] Error build_pedido_message:', e)
        return f"Pedido {getattr(pedido,'numero_pedido','')} Estado: {getattr(pedido,'estado','')} Total: ${getattr(pedido,'total',0):.2f}"
