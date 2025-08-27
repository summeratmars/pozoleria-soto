import time
import json
from queue import Queue, Empty
from threading import Lock

# Diccionario: numero_pedido -> set/list de colas de subscriptores
_subs = {}
_lock = Lock()

HEARTBEAT_INTERVAL = 25  # segundos


def subscribe_pedido(numero_pedido: str) -> Queue:
    q = Queue()
    with _lock:
        _subs.setdefault(numero_pedido, []).append(q)
    return q


def unsubscribe_pedido(numero_pedido: str, q: Queue):
    with _lock:
        lista = _subs.get(numero_pedido, [])
        if q in lista:
            lista.remove(q)
        if not lista and numero_pedido in _subs:
            _subs.pop(numero_pedido, None)


def broadcast_pedido_estado(numero_pedido: str, estado: str, extra: dict | None = None):
    payload = {"numero": numero_pedido, "estado": estado}
    if extra:
        payload.update(extra)
    data = json.dumps(payload)
    with _lock:
        for q in list(_subs.get(numero_pedido, [])):
            try:
                q.put_nowait(data)
            except Exception:
                # Si la cola está llena o error, ignorar y continuar
                pass
    try:
        print(f"[SSE] Broadcast -> Pedido {numero_pedido} Estado {estado} Subs={len(_subs.get(numero_pedido, []))}")
    except Exception:
        pass


def sse_stream(numero_pedido: str):
    q = subscribe_pedido(numero_pedido)
    last_heartbeat = time.time()
    try:
        while True:
            # Heartbeat para mantener conexión viva
            now = time.time()
            if now - last_heartbeat > HEARTBEAT_INTERVAL:
                yield ': ping\n\n'
                last_heartbeat = now
            try:
                msg = q.get(timeout=1)
            except Empty:
                continue
            yield f'data: {msg}\n\n'
    finally:
        unsubscribe_pedido(numero_pedido, q)
