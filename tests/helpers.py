from estudo.registro import Registro, registrar


def reg(con, ref, gab, resp, topico="LGPD.DIR", conf=2, tipo="", data="2026-11-10T10:00:00",
        fonte="p", confundido="", explicita="1"):
    return registrar(con, Registro(
        data=data, fonte=fonte, referencia=str(ref), gabarito=gab, arvore="", topico=topico,
        resposta=resp, confianca=str(conf), confianca_explicita=explicita, tipo_erro=tipo,
        topico_confundido=confundido))
