import os
import asyncio
import logging
import httpx
import re
import random
from datetime import datetime
import pytz
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
TZ_BR            = pytz.timezone("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JoaoCriptoBot")

EMOJIS = ["🚀", "📈", "💰", "🔥", "⚡", "💡", "🧠", "👀", "🌐", "📊"]

ABERTURAS = [
    "Fala pessoal, aqui é o João Cripto!",
    "E aí galera, João Cripto aqui!",
    "Olá investidores, João Cripto falando!",
    "Bora que bora, aqui é o João Cripto!",
    "Fala cripto família, João Cripto aqui!",
]

FECHAMENTOS = [
    "O mercado cripto não espera. Quem acumula agora, colhe depois do próximo Halving em 2028!",
    "Bitcoin abaixo de 100k ainda é oportunidade. Os grandes já estão posicionados.",
    "Enquanto a maioria dorme, os espertos acumulam. Seja esperto!",
    "DCA todo mês é a estratégia mais simples e poderosa do cripto. Não pare!",
    "O próximo bull run vai surpreender muita gente. Esteja preparado!",
]

CTA = "💰 Quer saber quanto você pode ter na próxima ATH?\n👉 Calculadora DCA gratuita: https://joao-cripto-btc.netlify.app/"

def periodo_do_dia():
    h = datetime.now(TZ_BR).hour
    if h < 12:  return "🌅 BOM DIA"
    if h < 18:  return "☀️ BOA TARDE"
    return "🌙 BOA NOITE"

async def buscar_noticias_newsdata():
    queries = [
        "bitcoin",
        "criptomoeda",
        "blockchain ethereum",
        "halving bitcoin",
        "mercado cripto brasil",
    ]
    todas = []
    vistos = set()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for query in queries:
                if len(todas) >= 7:
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
                    for n in r.json().get("results", []):
                        titulo = n.get("title", "")
                        if titulo and titulo not in vistos:
                            vistos.add(titulo)
                            todas.append(n)
                            if len(todas) >= 7:
                                break
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.error(f"Erro query '{query}': {e}")
    except Exception as e:
        log.error(f"Erro NewsData: {e}")
    return todas

async def buscar_rss(feeds_config):
    noticias = []
    vistos = set()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for feed_url, fonte in feeds_config:
                try:
                    r = await client.get(feed_url, headers={"User-Agent": "Mozilla/5.0"})
                    r.raise_for_status()
                    items = re.findall(r'<item>(.*?)</item>', r.text, re.DOTALL)
                    for item in items[:5]:
                        titulo_m = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
                        link_m   = re.search(r'<link>(.*?)</link>', item) or re.search(r'<guid>(.*?)</guid>', item)
                        desc_m   = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
                        if titulo_m:
                            titulo = re.sub(r'<[^>]+>', '', titulo_m.group(1)).strip()
                            if titulo and titulo not in vistos and len(titulo) > 15:
                                vistos.add(titulo)
                                desc = re.sub(r'<[^>]+>', '', desc_m.group(1) if desc_m else '')[:300].strip()
                                noticias.append({"title": titulo, "link": link_m.group(1).strip() if link_m else "", "description": desc, "fonte": fonte})
                    log.info(f"RSS {fonte}: ok")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    log.error(f"Erro RSS {fonte}: {e}")
    except Exception as e:
        log.error(f"Erro geral RSS: {e}")
    return noticias

async def buscar_noticias_tradingview():
    feeds = [
        ("https://br.cointelegraph.com/rss", "CoinTelegraph"),
        ("https://br.cointelegraph.com/rss/tag/bitcoin", "CoinTelegraph"),
        ("https://br.beincrypto.com/feed/", "BeInCrypto"),
        ("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk"),
        ("https://livecoins.com.br/feed/", "LiveCoins"),
    ]
    return await buscar_rss(feeds)

async def buscar_noticias():
    log.info("Buscando noticias...")
    nd, tv = await asyncio.gather(
        buscar_noticias_newsdata(),
        buscar_noticias_tradingview()
    )
    for n in nd: n["fonte"] = "NewsData"
    todas = []
    vistos = set()
    nd_count = tv_count = 0
    for n in nd:
        t = n.get("title","")
        if t not in vistos and nd_count < 5:
            vistos.add(t)
            todas.append(n)
            nd_count += 1
    for n in tv:
        t = n.get("title","")
        if t not in vistos and tv_count < 5:
            vistos.add(t)
            todas.append(n)
            tv_count += 1
    log.info(f"Total: {len(todas)} noticias ({nd_count} NewsData + {tv_count} RSS)")
    return todas[:15]

async def buscar_preco_btc():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids":"bitcoin","vs_currencies":"brl,usd","include_24hr_change":"true"}
            )
            r.raise_for_status()
            btc = r.json().get("bitcoin", {})
            return {"brl": btc.get("brl",0), "usd": btc.get("usd",0), "change": btc.get("brl_24h_change",0)}
    except Exception as e:
        log.error(f"Erro preco: {e}")
        return None

def gerar_roteiro(noticia, preco=None):
    titulo = noticia.get("title", "")
    descricao = re.sub(r'<[^>]+>', '', noticia.get("description", "") or "").strip()
    descricao = descricao[:300]

    abertura = random.choice(ABERTURAS)
    fechamento = random.choice(FECHAMENTOS)

    preco_txt = ""
    if preco:
        sinal = "em alta" if preco["change"] >= 0 else "em queda"
        brl = f"R$ {preco['brl']:,.0f}".replace(",", ".")
        chg = f"{abs(preco['change']):.1f}%"
        preco_txt = f"O Bitcoin está {sinal} {chg} hoje, valendo {brl}.\n\n"

    contexto = f"{descricao}\n\n" if descricao and len(descricao) > 50 else ""

    return f"""{abertura}

{preco_txt}A notícia de hoje é sobre: {titulo}.

{contexto}{fechamento}

{CTA}""".strip()

def limpar_html(texto):
    return texto.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def montar_cabecalho(preco, total_noticias):
    periodo = periodo_do_dia()
    now = datetime.now(TZ_BR).strftime("%d/%m/%Y %H:%M")
    if preco:
        sinal = "▲" if preco["change"] >= 0 else "▼"
        cor   = "🟢" if preco["change"] >= 0 else "🔴"
        brl   = f"R$ {preco['brl']:,.0f}".replace(",",".")
        usd   = f"US$ {preco['usd']:,.0f}".replace(",",".")
        chg   = f"{preco['change']:+.2f}%"
        linha_preco = f"{cor} <b>BTC:</b> {brl} ({usd}) {sinal} {chg} (24h)"
    else:
        linha_preco = "⚠️ Preço indisponível"

    return f"""<b>₿ JOÃO CRIPTO — {periodo}</b>
📅 {now} | Brasília

{linha_preco}

━━━━━━━━━━━━━━━━━━━━
📰 <b>{total_noticias} NOTÍCIAS + ROTEIROS DO DIA</b>
━━━━━━━━━━━━━━━━━━━━

💡 <i>Escolha as notícias que quer virar vídeo e use o roteiro pronto!</i>

{CTA}"""

def montar_post_noticia(noticia, preco, numero, total):
    titulo  = limpar_html(noticia.get("title","Sem título"))
    url     = noticia.get("link") or noticia.get("source_url") or ""
    fonte   = noticia.get("fonte","")
    em      = EMOJIS[(numero-1) % len(EMOJIS)]
    roteiro = limpar_html(gerar_roteiro(noticia, preco if numero == 1 else None))
    fonte_badge = f" <code>[{fonte}]</code>" if fonte else ""
    link_txt = f'\n🔗 <a href="{url}">Leia mais</a>' if url else ""

    return f"""{em} <b>NOTÍCIA {numero}/{total}</b>{fonte_badge}

<b>{titulo}</b>{link_txt}

🎬 <b>ROTEIRO:</b>
<i>{roteiro}</i>

━━━━━━━━━━━━━━━━━━━━"""

async def postar_noticias():
    log.info(f"Iniciando post — {datetime.now(TZ_BR).strftime('%H:%M')} BRT")
    bot      = Bot(token=TELEGRAM_TOKEN)
    noticias = await buscar_noticias()
    preco    = await buscar_preco_btc()

    if not noticias:
        log.warning("Sem noticias")
        return

    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=montar_cabecalho(preco, len(noticias)),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        log.info("Cabecalho enviado!")
    except Exception as e:
        log.error(f"Erro cabecalho: {e}")

    await asyncio.sleep(2)

    for i, noticia in enumerate(noticias):
        try:
            msg = montar_post_noticia(noticia, preco, i+1, len(noticias))
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            log.info(f"Noticia {i+1}/{len(noticias)} enviada! [{noticia.get('fonte','')}]")
            await asyncio.sleep(2)
        except Exception as e:
            log.error(f"Erro noticia {i+1}: {e}")

async def main():
    log.info("Joao Cripto Bot iniciando...")
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    for horario in HORARIOS:
        hora, minuto = horario.split(":")
        scheduler.add_job(postar_noticias, "cron", hour=int(hora), minute=int(minuto), id=f"post_{horario}")
        log.info(f"Agendado para {horario}")
    scheduler.start()
    log.info("Bot rodando! Aguardando horarios agendados...")
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
