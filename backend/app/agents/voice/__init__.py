import logging

# A raiz fica em WARNING (sem `basicConfig`), por isso os `logger.info` da voz — texto ouvido, resposta, tempos —
# nunca chegavam aos logs do Fly. Só o módulo da voz passa a falar; ligar o INFO na raiz enchia o log de pedidos HTTP.
_log = logging.getLogger(__name__)
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)
    _log.propagate = False
