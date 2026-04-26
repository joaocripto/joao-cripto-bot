import os
import asyncio
import logging
import httpx
import re
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════
# CONFIGURAÇÕES
# ══════════════════════════════════════
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NEWSDATA_KEY     = os.getenv("NEWSDATA_KEY")
HORARIOS         = ["08:00", "14:00", "20:00"]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JoaoCriptoBot")

EMOJIS = ["🚀", "📈", "💰", "🔥", "⚡", "💡", "🧠", "👀", "🌐", "📊"]

def periodo_do_dia():
    h = datetime.now().hour
    if h < 12:  return "🌅 BOM DIA"
    if h < 18:  return "☀️ BOA TARDE"
    return "🌙 BOA NOITE"

async def buscar_noticias():
    """Busca de múltiplas queries pra ter variedade"""
    queries = [
        "bitcoin",
        "criptomoeda",
        "blockchain ethereum",
        "halving bitcoin 2028",
        "mercado cripto brasil",
    ]
    todas = []
    vistos = set()

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for query in queries:
                if len(todas) >= 5:
                    break
                try:
                    r = await client.get(
                        "https://newsdata.io/api/1/news",
                        params={
                            "apikey": NEWSDATA_KEY,
                            "q": query,
                            "language": "pt",
                            "category": "business,technology",
                        }
                    )
                    r.raise_for_status()
                    resultados = r.json().get("results", [])
                    for n in resultados:
                        titulo = n.get("title", "")
                        if titulo and titulo not in vistos:
                            vistos.add(titulo)
                            todas.append(n)
                            if len(todas) >= 5:
                                break
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.error(f"Erro query '{query}': {e}")
                    continue
    except Exception as e:
        log.error(f"Erro geral noticias: {e}")

    # fallback inglês se não achou em pt
    if not todas:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://newsdata.io/api/1/news",
                    params={
                        "apikey": NEWSDATA_KEY,
                        "q": "bitcoin OR crypto",
                        "language": "en",
                        "category": "business,technology",
                    }
                )
                r.raise_for_status()
                todas = r.json().get("results", [])[:5]
        except Exception as e:
            log.error(f"Erro fallback: {e}")

    return todas[:5]

async def buscar_preco_btc():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin",
                    "vs_currencies": "brl,usd",
                    "include_24hr_change": "true"
                }
            )
            r.raise_for_status()
            btc = r.json().get("bitcoin", {})
            return {
                "brl": btc.get("brl", 0),
                "usd": btc.get("usd", 0),
                "change": btc.get("brl_24h_change", 0)
            }
    except Exception as e:
        log.error(f"Erro preco: {e}")
        return None

def gerar_roteiro(noticia, preco=None):
    """Gera roteiro de ~1 minuto para o vídeo"""
    titulo = noticia.get("title", "")
    descricao = re.sub(r'<[^>]+>', '', noticia.get("description", "") or "")
    descricao = descricao[:250] if len(descricao) > 250 else descricao

    preco_txt = ""
    if preco:
        sinal = "em alta" if preco["change"] >= 0 else "em queda"
        brl = f"R$ {preco['brl']:,.0f}".replace(",", ".")
        chg = f"{abs(preco['change']):.1f}%"
        preco_txt = f"O Bitcoin está {sinal} {chg} hoje, valendo {brl}. "

    roteiro = f"""Fala pessoal, aqui é o João Cripto!

{preco_txt}A notícia de hoje é importante: {titulo}.

{descricao}

Isso mostra que o mercado cripto continua evoluindo. Quem está acumulando agora, vai agradecer depois do próximo Halving em 2028!

Quer saber quanto você pode ter até a próxima ATH? Acessa minha calculadora DCA gratuita no link da bio e simula com o valor que você consegue investir por semana.

Os grandes pensam diferente. Até a próxima, João Cripto!"""

    return roteiro.strip()

def limpar_html(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def montar_post_noticia(noticia, preco, numero, total):
    """Monta post individual com notícia + roteiro"""
    titulo = limpar_html(noticia.get("title", "Sem título"))
    url    = noticia.get("link") or noticia.get("source_url") or ""
    em     = EMOJIS[(numero - 1) % len(EMOJIS)]
    roteiro = gerar_roteiro(noticia, preco if numero == 1 else None)
    roteiro_limpo = limpar_html(roteiro)

    link_txt = f'\n🔗 <a href="{url}">Leia mais</a>' if url else ""

    return f"""{em} <b>NOTÍCIA {numero}/{total}</b>

<b>{titulo}</b>{link_txt}

━━━━━━━━━━━━━━━━━━━━
🎬 <b>ROTEIRO PARA O VÍDEO (1 min):</b>
━━━━━━━━━━━━━━━━━━━━
<i>{roteiro_limpo}</i>

#Bitcoin #Cripto #JoaoCripto #DCA #Halving2028"""

def montar_cabecalho(preco):
    """Monta mensagem de abertura com preço do BTC"""
    periodo = periodo_do_dia()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    if preco:
        sinal = "▲" if preco["change"] >= 0 else "▼"
        cor   = "🟢" if preco["change"] >= 0 else "🔴"
        brl   = f"R$ {preco['brl']:,.0f}".replace(",", ".")
        usd   = f"US$ {preco['usd']:,.0f}".replace(",", ".")
        chg   = f"{preco['change']:+.2f}%"
        linha_preco = f"{cor} <b>BTC:</b> {brl} ({usd}) {sinal} {chg} (24h)"
    else:
        linha_preco = "⚠️ Preço indisponível no momento"

    return f"""<b>₿ JOÃO CRIPTO — {periodo}</b>
📅 {now} | Brasília

{linha_preco}

━━━━━━━━━━━━━━━━━━━━
📰 <b>NOTÍCIAS + ROTEIROS DO DIA</b>
━━━━━━━━━━━━━━━━━━━━

💡 <i>Use os roteiros abaixo para gerar seus vídeos no HeyGen!</i>

🔗 Calculadora DCA gratuita:
joao-cripto-btc.netlify.app"""

async def postar_noticias():
    log.info(f"Iniciando post — {datetime.now().strftime('%H:%M')}")
    bot      = Bot(token=TELEGRAM_TOKEN)
    noticias = await buscar_noticias()
    preco    = await buscar_preco_btc()

    if not noticias:
        log.warning("Sem noticias")
        return

    # 1. Posta cabeçalho com preço
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=montar_cabecalho(preco),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        log.info("Cabecalho enviado!")
    except Exception as e:
        log.error(f"Erro cabecalho: {e}")

    await asyncio.sleep(2)

    # 2. Posta uma mensagem por notícia com roteiro
    total = len(noticias)
    for i, noticia in enumerate(noticias):
        try:
            msg = montar_post_noticia(noticia, preco, i + 1, total)
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            log.info(f"Noticia {i+1}/{total} enviada!")
            await asyncio.sleep(3)  # pausa entre mensagens
        except Exception as e:
            log.error(f"Erro noticia {i+1}: {e}")

async def main():
    log.info("Joao Cripto Bot iniciando...")
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    for horario in HORARIOS:
        hora, minuto = horario.split(":")
        scheduler.add_job(
            postar_noticias, "cron",
            hour=int(hora), minute=int(minuto),
            id=f"post_{horario}"
        )
        log.info(f"Agendado para {horario}")

    scheduler.start()
    log.info("Bot rodando!")
    await postar_noticias()

    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
