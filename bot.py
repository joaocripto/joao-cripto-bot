import os
import asyncio
import logging
from datetime import datetime
import httpx
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════
# CONFIGURAÇÕES — preencha aqui
# ══════════════════════════════════════
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "SEU_CHAT_ID_AQUI")
NEWSDATA_KEY     = os.getenv("NEWSDATA_KEY", "SUA_KEY_AQUI")

# Horários de postagem (hora de Brasília)
HORARIOS = ["08:00", "14:00", "20:00"]

# ══════════════════════════════════════
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JoaoCriptoBot")

EMOJIS = ["🚀", "📈", "💰", "🔥", "⚡", "📰", "🔵", "💡", "🧠", "👀"]

def emoji_noticia(i):
    return EMOJIS[i % len(EMOJIS)]

def periodo_do_dia():
    h = datetime.now().hour
    if h < 12:  return "🌅 BOM DIA"
    if h < 18:  return "☀️ BOA TARDE"
    return "🌙 BOA NOITE"

async def buscar_noticias():
    """Busca notícias cripto no NewsData.io (gratuito)"""
    url = "https://newsdata.io/api/1/news"
    params = {
        "apikey": NEWSDATA_KEY,
        "q": "bitcoin OR crypto OR cryptocurrency",
        "language": "pt,en",
        "category": "business,technology",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            return data.get("results", [])[:5]
    except Exception as e:
        log.error(f"Erro ao buscar notícias: {e}")
        return []

async def buscar_preco_btc():
    """Busca preço atual do BTC em BRL"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin", "vs_currencies": "brl,usd", "include_24hr_change": "true"}
            )
            r.raise_for_status()
            data = r.json()
            btc = data.get("bitcoin", {})
            return {
                "brl": btc.get("brl", 0),
                "usd": btc.get("usd", 0),
                "change": btc.get("brl_24h_change", 0)
            }
    except Exception as e:
        log.error(f"Erro ao buscar preço: {e}")
        return None

def formatar_preco(preco):
    if not preco:
        return ""
    sinal = "▲" if preco["change"] >= 0 else "▼"
    cor   = "🟢" if preco["change"] >= 0 else "🔴"
    brl   = f"R$ {preco['brl']:,.0f}".replace(",", ".")
    usd   = f"US$ {preco['usd']:,.0f}".replace(",", ".")
    chg   = f"{preco['change']:+.2f}%"
    return f"{cor} *BTC:* {brl} ({usd}) {sinal} {chg} (24h)"

def formatar_mensagem(noticias, preco):
    periodo = periodo_do_dia()
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    linhas = [
        f"*₿ JOÃO CRIPTO — {periodo}*",
        f"📅 {now} | Brasília",
        "",
        formatar_preco(preco),
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "*📰 PRINCIPAIS NOTÍCIAS CRIPTO*",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not noticias:
        linhas.append("⚠️ Nenhuma notícia encontrada no momento.")
    else:
        for i, n in enumerate(noticias, 1):
            titulo = n.get("title", "Sem título")
            url    = n.get("link", n.get("source_url", ""))
            em     = emoji_noticia(i)
            # Limpa caracteres especiais do título pro Markdown
            titulo_safe = titulo.replace("[","(").replace("]",")").replace("*","").replace("_","")
            linhas.append(f"{em} *{i}\\. * [{titulo_safe}]({url})")
            linhas.append("")

    linhas += [
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "💡 *Dica João Cripto:*",
        "_Acumule todo dia. O tempo no mercado bate o timing do mercado._",
        "",
        "🔗 *Calculadora DCA gratuita:*",
        "joao\\-cripto\\-btc\\.netlify\\.app",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "👊 *Os grandes pensam diferente\\!*",
        "#Bitcoin #Cripto #JoãoCripto #DCA #Halving2028"
    ]

    return "\n".join(linhas)

async def postar_noticias():
    log.info(f"Postando notícias — {datetime.now().strftime('%H:%M')}")
    bot      = Bot(token=TELEGRAM_TOKEN)
    noticias = await buscar_noticias()
    preco    = await buscar_preco_btc()
    msg      = formatar_mensagem(noticias, preco)

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=False
        )
        log.info("✅ Mensagem enviada com sucesso!")
    except Exception as e:
        log.error(f"Erro ao enviar mensagem: {e}")
        # tenta sem markdown se falhar
        try:
            msg_simples = msg.replace("*","").replace("_","").replace("`","").replace("\\","")
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg_simples)
            log.info("✅ Mensagem enviada (sem formatação)")
        except Exception as e2:
            log.error(f"Erro fatal: {e2}")

async def main():
    log.info("🤖 João Cripto Bot iniciando...")

    # Agenda os horários
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    for horario in HORARIOS:
        hora, minuto = horario.split(":")
        scheduler.add_job(
            postar_noticias,
            "cron",
            hour=int(hora),
            minute=int(minuto),
            id=f"post_{horario}"
        )
        log.info(f"⏰ Agendado para {horario}")

    scheduler.start()
    log.info("✅ Bot rodando! Aguardando horários agendados...")

    # Posta uma vez agora pra testar
    log.info("📤 Enviando post de teste agora...")
    await postar_noticias()

    # Mantém rodando
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
