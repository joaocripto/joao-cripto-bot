import os
import asyncio
import logging
from datetime import datetime
import httpx
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════
# CONFIGURAÇÕES
# ══════════════════════════════════════
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "SEU_CHAT_ID_AQUI")
NEWSDATA_KEY     = os.getenv("NEWSDATA_KEY", "SUA_KEY_AQUI")
HORARIOS         = ["08:00", "14:00", "20:00"]

# ══════════════════════════════════════
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JoaoCriptoBot")

EMOJIS = ["🚀", "📈", "💰", "🔥", "⚡", "📰", "💡", "🧠", "👀", "🌐"]

def periodo_do_dia():
    h = datetime.now().hour
    if h < 12:  return "🌅 BOM DIA"
    if h < 18:  return "☀️ BOA TARDE"
    return "🌙 BOA NOITE"

async def buscar_noticias():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://newsdata.io/api/1/news",
                params={
                    "apikey": NEWSDATA_KEY,
                    "q": "bitcoin OR crypto OR cryptocurrency",
                    "language": "pt,en",
                    "category": "business,technology",
                }
            )
            r.raise_for_status()
            return r.json().get("results", [])[:5]
    except Exception as e:
        log.error(f"Erro noticias: {e}")
        return []

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

def limpar_html(texto):
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def montar_mensagem(noticias, preco):
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
        linha_preco = "Preco indisponivel no momento"

    itens = ""
    if not noticias:
        itens = "Nenhuma noticia encontrada no momento.\n"
    else:
        for i, n in enumerate(noticias):
            titulo = limpar_html(n.get("title", "Sem titulo"))
            url    = n.get("link") or n.get("source_url") or ""
            em     = EMOJIS[i % len(EMOJIS)]
            if url:
                itens += f'{em} <a href="{url}">{titulo}</a>\n\n'
            else:
                itens += f"{em} {titulo}\n\n"

    msg = f"""<b>JOAO CRIPTO {periodo}</b>
Data: {now} Brasilia

{linha_preco}

PRINCIPAIS NOTICIAS CRIPTO

{itens}
Dica Joao Cripto:
<i>Acumule todo dia. O tempo no mercado bate o timing.</i>

Calculadora DCA gratuita:
joao-cripto-btc.netlify.app

Os grandes pensam diferente!
#Bitcoin #Cripto #JoaoCripto #DCA #Halving2028"""

    return msg

async def postar_noticias():
    log.info(f"Postando — {datetime.now().strftime('%H:%M')}")
    bot      = Bot(token=TELEGRAM_TOKEN)
    noticias = await buscar_noticias()
    preco    = await buscar_preco_btc()
    msg      = montar_mensagem(noticias, preco)

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        log.info("Mensagem enviada com sucesso!")
    except Exception as e:
        log.error(f"Erro: {e}")
        try:
            import re
            msg_plain = re.sub(r'<[^>]+>', '', msg).replace("&amp;","&").replace("&lt;","<").replace("&gt;",">")
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg_plain)
            log.info("Mensagem enviada sem formatacao")
        except Exception as e2:
            log.error(f"Erro fatal: {e2}")

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
